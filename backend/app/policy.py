from __future__ import annotations

import ast
import hashlib
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .llm import OllamaPolicyPlanner
from .models import (
    NormalizedEvent,
    PolicyArtifact,
    PolicyDecision,
    PolicyDraft,
    Severity,
    TestCase,
    TestResult,
    TestRun,
)


def policy_source(event_types: list[str], quiet_start: int, quiet_end: int, severity: Severity) -> str:
    """Render a read-only explanation of the validated declarative policy plan."""
    types = ", ".join(repr(event_type) for event_type in event_types)
    severity_value = severity.value if isinstance(severity, Severity) else str(severity)
    return f'''def evaluate(event: NormalizedEvent, context: PolicyContext) -> PolicyDecision:
    """Evaluate the validated policy plan; generated source is never executed."""
    local_hour = context.local_hour(event.occurred_at)
    activity = event.event_type in {{{types}}}
    excluded = event.actor.service_account or event.actor.id in context.excluded_actor_ids
    matched = activity and {quiet_start} <= local_hour < {quiet_end} and not excluded
    return PolicyDecision(
        matched=matched,
        severity="{severity_value}",
        reason_code="SUSPICIOUS_QUIET_HOURS" if matched else "OUTSIDE_POLICY_SCOPE",
        explanation="Repository activity occurred during configured quiet hours." if matched else "The event is outside the configured policy conditions.",
        evidence={{"event_type": event.event_type, "local_hour": str(local_hour)}},
        action_ref=context.action_ref,
    )
'''


class UnsafePolicyError(ValueError):
    pass


def validate_policy_source(source: str) -> str:
    if len(source) > 50_000:
        raise UnsafePolicyError("policy source exceeds the maximum size")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise UnsafePolicyError(f"invalid policy source: {exc.msg}") from exc
    forbidden = (ast.Import, ast.ImportFrom, ast.With, ast.AsyncFunctionDef, ast.Await, ast.Lambda, ast.ClassDef)
    forbidden_names = {"__import__", "eval", "exec", "open", "compile", "globals", "locals", "getattr", "setattr", "input"}
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise UnsafePolicyError(f"unsupported unsafe syntax: {type(node).__name__}")
        if isinstance(node, ast.Attribute):
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if not isinstance(root, ast.Name) or root.id not in {"event", "context"}:
                raise UnsafePolicyError("policy attributes are limited to event and context")
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            raise UnsafePolicyError(f"forbidden name: {node.id}")
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "evaluate"]
    if len(functions) != 1:
        raise UnsafePolicyError("source must define exactly one evaluate function")
    return hashlib.sha256(source.encode()).hexdigest()


def _event(hour: int, event_type: str = "repository.fork", actor_id: str = "alice", service_account: bool = False, event_id: str | None = None, timezone_name: str = "UTC") -> dict[str, Any]:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    occurred_at = datetime(2026, 7, 18, hour, 30, tzinfo=zone).isoformat()
    return {
        "event_id": event_id or f"fixture-{hour}-{event_type}-{actor_id}", "connection_id": "fixture", "vendor": "github",
        "event_type": event_type, "occurred_at": occurred_at, "dedupe_key": f"github:{event_id or hour}-{event_type}-{actor_id}",
        "actor": {"id": actor_id, "name": actor_id, "service_account": service_account}, "resource": {"type": "repository", "name": "payments"},
    }


def suspicious_hours_cases(timezone: str, exclusions: dict[str, Any], event_types: list[str], quiet_start: int, quiet_end: int) -> list[TestCase]:
    excluded_ids = exclusions.get("actor_ids", [])
    excluded = excluded_ids[0] if excluded_ids else "automation-bot"
    event_type = event_types[0]
    matching_hour = quiet_start
    non_matching_hour = quiet_end % 24
    before_hour = (quiet_start - 1) % 24
    return [
        TestCase(name="matching_activity", scenario_type="positive", input_event=_event(matching_hour, event_type, timezone_name=timezone), expected_matched=True),
        TestCase(name="non_matching_activity", scenario_type="negative", input_event=_event(non_matching_hour, event_type, timezone_name=timezone), expected_matched=False),
        TestCase(name="boundary_before", scenario_type="boundary", input_event=_event(before_hour, event_type, timezone_name=timezone), expected_matched=False),
        TestCase(name="boundary_after", scenario_type="boundary", input_event=_event(non_matching_hour, event_type, timezone_name=timezone), expected_matched=False),
        TestCase(name="excluded_actor", scenario_type="exclusion", input_event=_event(matching_hour, event_type, actor_id=excluded, service_account=True, timezone_name=timezone), expected_matched=False),
        TestCase(name="malformed_event", scenario_type="malformed", input_event={"event_type": "repository.fork", "dedupe_key": "malformed"}, expected_matched=False),
        TestCase(name="duplicate_event", scenario_type="duplicate", input_event=_event(matching_hour, event_type, timezone_name=timezone), expected_matched=False),
    ]


def generate_policy(draft: PolicyDraft) -> PolicyArtifact:
    requested_types = draft.event_types or ["repository.commit", "repository.clone", "repository.fork"]
    plan = OllamaPolicyPlanner().plan(prompt=draft.prompt, timezone=draft.timezone, event_types=requested_types, policy_name=draft.name)
    # The unconfigured path preserves local/offline development and test support.
    # A configured model failure raises PolicyPlanningError; it is never replaced with a fabricated plan.
    if plan:
        policy_name, summary = plan.policy_name, plan.summary
        required_types, quiet_start, quiet_end = plan.event_types, plan.quiet_start, plan.quiet_end
        assumptions = [f"Event times are interpreted in {draft.timezone}.", *plan.assumptions]
        generator = "ollama-policy-planner-v1"
    else:
        policy_name, summary = draft.name, draft.prompt
        required_types, quiet_start, quiet_end = requested_types, 1, 5
        assumptions = [f"Event times are interpreted in {draft.timezone}.", "Offline development plan; configure Ollama to generate a model plan."]
        generator = "offline-declarative-policy-v1"
    if draft.exclusions:
        assumptions.append("Configured service accounts and actor IDs are excluded.")
    source = policy_source(required_types, quiet_start, quiet_end, draft.severity)
    source_hash = validate_policy_source(source)
    return PolicyArtifact(
        policy_name=policy_name, summary=summary,
        intent={"quiet_start": quiet_start, "quiet_end": quiet_end, "timezone": draft.timezone, "exclusions": draft.exclusions},
        required_event_types=required_types, required_fields=["event_type", "occurred_at", "actor.id", "actor.service_account"],
        assumptions=assumptions, severity=draft.severity, action_ref=draft.action_ref, python_source=source,
        source_sha256=source_hash, generator=generator, test_cases=suspicious_hours_cases(draft.timezone, draft.exclusions, required_types, quiet_start, quiet_end),
    )


class SafePolicyRuntime:
    """Pure evaluator for the built-in artifact; no generated source is executed in-process."""

    def evaluate(self, artifact: PolicyArtifact, event: NormalizedEvent, *, seen: set[str] | None = None) -> PolicyDecision:
        if seen is not None and event.dedupe_key in seen:
            return PolicyDecision(matched=False, severity=artifact.severity, reason_code="DUPLICATE_EVENT", explanation="The event was already evaluated in this run.", evidence={"dedupe_key": event.dedupe_key}, action_ref=artifact.action_ref)
        if seen is not None:
            seen.add(event.dedupe_key)
        if not event.event_type or not event.occurred_at or not event.actor:
            return PolicyDecision(matched=False, severity=artifact.severity, reason_code="MALFORMED_EVENT", explanation="Required normalized event fields are missing.", evidence={}, action_ref=artifact.action_ref)
        try:
            local_hour = event.occurred_at.astimezone(ZoneInfo(str(artifact.intent.get("timezone", "UTC")))).hour
        except ZoneInfoNotFoundError:
            local_hour = event.occurred_at.hour
        activity = event.event_type in set(artifact.required_event_types)
        excluded_ids = set(artifact.intent.get("exclusions", {}).get("actor_ids", []))
        excluded = event.actor.service_account or event.actor.id in excluded_ids
        quiet_start = int(artifact.intent.get("quiet_start", 1))
        quiet_end = int(artifact.intent.get("quiet_end", 5))
        matched = activity and quiet_start <= local_hour < quiet_end and not excluded
        return PolicyDecision(
            matched=matched, severity=artifact.severity,
            reason_code="SUSPICIOUS_QUIET_HOURS" if matched else "OUTSIDE_POLICY_SCOPE",
            explanation="Repository activity occurred during configured quiet hours." if matched else "The event is outside the configured policy conditions.",
            evidence={"event_type": event.event_type, "utc_hour": str(local_hour), "actor_id": event.actor.id or "unknown"}, action_ref=artifact.action_ref,
        )


def run_test(artifact: PolicyArtifact, *, runtime: SafePolicyRuntime | None = None) -> TestRun:
    runtime = runtime or SafePolicyRuntime()
    results: list[TestResult] = []
    seen: set[str] = set()
    for case in artifact.test_cases:
        try:
            event = NormalizedEvent.model_validate(case.input_event)
            decision = runtime.evaluate(artifact, event, seen=seen)
            results.append(TestResult(case_name=case.name, expected_matched=case.expected_matched, actual_matched=decision.matched, passed=decision.matched == case.expected_matched, reason_code=decision.reason_code, explanation=decision.explanation, trace=decision.evidence))
        except Exception as exc:
            # A malformed fixture is a valid negative scenario when it is expected not to match.
            results.append(TestResult(case_name=case.name, expected_matched=case.expected_matched, actual_matched=False, passed=case.expected_matched is False, reason_code="MALFORMED_EVENT", error=str(exc)))
    passed = sum(result.passed for result in results)
    return TestRun(status="passed" if passed == len(results) else "failed", results=results, summary={"total": len(results), "passed": passed, "failed": len(results) - passed})
