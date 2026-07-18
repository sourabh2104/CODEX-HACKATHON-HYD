from datetime import datetime, timezone

import pytest

from app.models import EventActor, EventResource, NormalizedEvent, PolicyDraft, Severity
from app.policy import SafePolicyRuntime, UnsafePolicyError, generate_policy, run_test, validate_policy_source


def draft(**overrides):
    values = {
        "workspace_id": "workspace-a",
        "name": "Suspicious hours",
        "prompt": "Detect GitHub commit, clone, or fork activity between 01:00 and 05:00 unless the actor is automation.",
        "vendor": "github",
        "event_types": [],
        "timezone": "UTC",
        "business_hours": {},
        "exclusions": {"actor_ids": ["bot-1"]},
        "severity": Severity.HIGH,
    }
    values.update(overrides)
    return PolicyDraft(**values)


def test_suspicious_hours_generator_is_deterministic_and_complete():
    first = generate_policy(draft())
    second = generate_policy(draft())

    assert first.source_sha256 == second.source_sha256
    assert first.required_event_types == ["repository.commit", "repository.clone", "repository.fork"]
    assert {case.scenario_type for case in first.test_cases} == {"positive", "negative", "boundary", "exclusion", "malformed", "duplicate"}
    assert run_test(first).summary == {"total": 7, "passed": 7, "failed": 0}


def test_runtime_matches_only_quiet_hours_and_exclusions():
    artifact = generate_policy(draft())
    runtime = SafePolicyRuntime()

    def event(hour, actor_id="alice", service_account=False):
        return NormalizedEvent(
            event_id=f"event-{hour}-{actor_id}", connection_id="conn", vendor="github", event_type="repository.fork",
            occurred_at=datetime(2026, 7, 18, hour, 30, tzinfo=timezone.utc), dedupe_key=f"github:event-{hour}-{actor_id}",
            actor=EventActor(id=actor_id, service_account=service_account), resource=EventResource(type="repository"),
        )

    assert runtime.evaluate(artifact, event(1)).matched is True
    assert runtime.evaluate(artifact, event(4)).matched is True
    assert runtime.evaluate(artifact, event(0)).matched is False
    assert runtime.evaluate(artifact, event(5)).matched is False
    assert runtime.evaluate(artifact, event(2, "bot-1")).matched is False
    assert runtime.evaluate(artifact, event(2, service_account=True)).matched is False


def test_duplicate_events_are_not_triggered_twice_in_one_run():
    artifact = generate_policy(draft())
    fixture = artifact.test_cases[0].input_event
    from app.models import NormalizedEvent

    event = NormalizedEvent.model_validate(fixture)
    seen = set()
    assert SafePolicyRuntime().evaluate(artifact, event, seen=seen).matched is True
    duplicate = SafePolicyRuntime().evaluate(artifact, event, seen=seen)
    assert duplicate.matched is False
    assert duplicate.reason_code == "DUPLICATE_EVENT"


@pytest.mark.parametrize("source", [
    "import os\ndef evaluate(event, context): return None",
    "def evaluate(event, context): return open('secrets')",
    "def evaluate(event, context): return __import__('os')",
])
def test_policy_source_rejects_unsafe_constructs(source):
    with pytest.raises(UnsafePolicyError):
        validate_policy_source(source)

