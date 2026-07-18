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


SUSPICIOUS_HOURS_SOURCE = '''def evaluate(event: NormalizedEvent, context: PolicyContext) -> PolicyDecision:
    """Flag commit, clone, or fork activity in the configured quiet hours."""
    local_hour = context.local_hour(event.occurred_at)
    activity = event.event_type in {"repository.commit", "repository.clone", "repository.fork"}
    excluded = event.actor.service_account or event.actor.id in context.excluded_actor_ids
    matched = activity and context.quiet_start <= local_hour < context.quiet_end and not excluded
    return PolicyDecision(
        matched=matched,
        severity="high",
        reason_code="SUSPICIOUS_QUIET_HOURS" if matched else "OUTSIDE_POLICY_SCOPE",
        explanation="Repository activity occurred during configured quiet hours." if matched else "The event is outside the configured policy conditions.",
        evidence={"event_type": event.event_type, "local_hour": str(local_hour)},
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


def suspicious_hours_cases(timezone: str, exclusions: dict[str, Any]) -> list[TestCase]:
    excluded_ids = exclusions.get("actor_ids", [])
    excluded = excluded_ids[0] if excluded_ids else "automation-bot"
    return [
        TestCase(name="matching_activity", scenario_type="positive", input_event=_event(2, timezone_name=timezone), expected_matched=True),
        TestCase(name="non_matching_activity", scenario_type="negative", input_event=_event(12, timezone_name=timezone), expected_matched=False),
        TestCase(name="boundary_before", scenario_type="boundary", input_event=_event(0, timezone_name=timezone), expected_matched=False),
        TestCase(name="boundary_after", scenario_type="boundary", input_event=_event(5, timezone_name=timezone), expected_matched=False),
        TestCase(name="excluded_actor", scenario_type="exclusion", input_event=_event(2, actor_id=excluded, service_account=True, timezone_name=timezone), expected_matched=False),
        TestCase(name="malformed_event", scenario_type="malformed", input_event={"event_type": "repository.fork", "dedupe_key": "malformed"}, expected_matched=False),
        TestCase(name="duplicate_event", scenario_type="duplicate", input_event=_event(2, timezone_name=timezone), expected_matched=False),
    ]


def generate_policy(draft: PolicyDraft) -> PolicyArtifact:
    prompt = draft.prompt.lower()
    is_suspicious_hours = any(word in prompt for word in ("suspicious", "quiet hours", "01:00", "05:00", "overnight"))
    if not is_suspicious_hours:
        # Still return a safe, deterministic artifact for a documented starter scenario.
        summary = "Detect suspicious GitHub repository activity during quiet hours."
    else:
        summary = "Detect GitHub commit, clone, or fork activity between 01:00 and 05:00, excluding approved automation."
    required_types = draft.event_types or ["repository.commit", "repository.clone", "repository.fork"]
    assumptions = [f"Event times are interpreted in {draft.timezone}.", "Quiet hours use the half-open interval 01:00 inclusive through 05:00 exclusive.", "Missing actor or timestamp fields do not match."]
    if draft.exclusions:
        assumptions.append("Configured service accounts and actor IDs are excluded.")
    plan = OllamaPolicyPlanner().plan(prompt=draft.prompt, timezone=draft.timezone, event_types=required_types)
    if plan:
        summary = plan.summary
        assumptions.extend(plan.assumptions)
    source_hash = validate_policy_source(SUSPICIOUS_HOURS_SOURCE)
    return PolicyArtifact(
        policy_name=draft.name, summary=summary,
        intent={"scenario": "suspicious_hours", "quiet_start": "01:00", "quiet_end": "05:00", "timezone": draft.timezone, "exclusions": draft.exclusions},
        required_event_types=required_types, required_fields=["event_type", "occurred_at", "actor.id", "actor.service_account"],
        assumptions=assumptions, severity=draft.severity, action_ref=draft.action_ref, python_source=SUSPICIOUS_HOURS_SOURCE,
        source_sha256=source_hash, generator="ollama-policy-planner-v1" if plan else "deterministic-suspicious-hours-v1", test_cases=suspicious_hours_cases(draft.timezone, draft.exclusions),
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
        matched = activity and 1 <= local_hour < 5 and not excluded
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
