import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.models import Check, CheckStatus, ConnectionTest
from app.repository import InMemoryRepository


@pytest.fixture(autouse=True)
def clean_repository(monkeypatch):
    main.repo = InMemoryRepository()
    def fake_test(connection):
        if connection.config.get("simulate") == "missing_scope":
            return ConnectionTest(status="degraded", checks=[Check(name="credentials", status=CheckStatus.PASSED), Check(name="api_reachability", status=CheckStatus.PASSED), Check(name="required_scopes", status=CheckStatus.FAILED, code="MISSING_AUDIT_SCOPE"), Check(name="event_subscription", status=CheckStatus.SKIPPED), Check(name="sample_event", status=CheckStatus.NOT_AVAILABLE)], remediation={"summary": "Grant organization audit-log access.", "steps": [], "test_actions": []})
        return ConnectionTest(status="passed", checks=[Check(name=name, status=CheckStatus.PASSED) for name in ["credentials", "api_reachability", "required_scopes", "event_subscription", "sample_event"]])
    monkeypatch.setattr(main.CONNECTORS["github"], "test_connection", fake_test)
    yield


@pytest.fixture
def client():
    return TestClient(main.app)


def headers(workspace="workspace-a"):
    return {"X-Workspace-ID": workspace, "X-Actor": "tester"}


def create_ready_connection(client, *, config=None):
    connection_config = {"personal_access_token": "test-token", "organization": "acme", **(config or {})}
    response = client.post("/api/v1/connections", headers=headers(), json={"vendor": "github", "name": "Acme GitHub", "secret_ref": "openbao://workspace/github", "config": connection_config})
    assert response.status_code == 201
    connection = response.json()
    assert "token" not in json.dumps(connection)
    assert "webhook_secret" not in json.dumps(connection)
    assert client.post(f"/api/v1/connections/{connection['id']}/test", headers=headers()).json()["status"] == "passed"
    enabled = client.post(f"/api/v1/connections/{connection['id']}/enable", headers=headers())
    assert enabled.status_code == 200
    return connection["id"]


def create_deployed_policy(client, connection_id, action_ref=None):
    response = client.post("/api/v1/policy-drafts", headers=headers(), json={
        "name": "Quiet hours policy", "prompt": "Detect suspicious GitHub activity between 01:00 and 05:00.", "vendor": "github", "severity": "high", "action_ref": action_ref,
    })
    draft_id = response.json()["id"]
    assert client.post(f"/api/v1/policy-drafts/{draft_id}/generate", headers=headers()).status_code == 200
    test = client.post(f"/api/v1/policy-drafts/{draft_id}/test", headers=headers())
    assert test.json()["status"] == "passed"
    deployed = client.post(f"/api/v1/policy-drafts/{draft_id}/deploy", headers=headers())
    assert deployed.status_code == 201
    return deployed.json()["policy"]["id"]


def test_connection_staged_diagnostics_and_lifecycle(client):
    response = client.post("/api/v1/connections", headers=headers(), json={"vendor": "github", "name": "Broken", "secret_ref": "openbao://x", "config": {"simulate": "missing_scope", "token": "never-return-this"}})
    connection = response.json()
    diagnostic = client.post(f"/api/v1/connections/{connection['id']}/test", headers=headers())
    assert diagnostic.json()["status"] == "degraded"
    checks = {item["name"]: item for item in diagnostic.json()["checks"]}
    assert checks["required_scopes"]["code"] == "MISSING_AUDIT_SCOPE"
    assert "audit" in diagnostic.json()["remediation"]["summary"]
    assert client.post(f"/api/v1/connections/{connection['id']}/enable", headers=headers()).status_code == 409

    good_id = create_ready_connection(client)
    disabled = client.post(f"/api/v1/connections/{good_id}/disable", headers=headers())
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["enabled"] is False


def test_policy_deploys_evaluates_webhook_and_records_dry_run_action(client):
    connection_id = create_ready_connection(client)
    action = client.post("/api/v1/actions", headers=headers(), json={"name": "Dry-run block", "action_type": "block", "mode": "dry_run", "provider": "github"}).json()
    policy_id = create_deployed_policy(client, connection_id, action["id"])
    payload = {
        "id": "delivery-123", "event_type": "repository.fork", "occurred_at": "2026-07-18T02:30:00Z",
        "actor": {"id": "alice", "login": "alice"}, "repository": {"id": "repo-1", "name": "payments", "organization": "acme"},
    }
    response = client.post(f"/api/v1/webhooks/github/{connection_id}", headers=headers(), content=json.dumps(payload))
    assert response.status_code == 200
    assert response.json()["duplicate"] is False
    evaluations = client.get("/api/v1/evaluations", headers=headers()).json()
    assert len(evaluations) == 1
    assert evaluations[0]["decision"]["matched"] is True
    assert evaluations[0]["decision"]["reason_code"] == "SUSPICIOUS_QUIET_HOURS"
    execution = main.repo.action_executions[evaluations[0]["action_execution_id"]]
    assert execution.status == "succeeded"
    assert execution.result["dry_run"] is True
    trigger = client.get(f"/api/v1/triggers/{evaluations[0]['id']}", headers=headers())
    assert trigger.status_code == 200
    assert trigger.json()["event"]["source"]["event_id"] == "delivery-123"

    duplicate = client.post(f"/api/v1/webhooks/github/{connection_id}", headers=headers(), content=json.dumps(payload))
    assert duplicate.json()["duplicate"] is True
    assert len(client.get("/api/v1/evaluations", headers=headers()).json()) == 1
    assert client.get("/api/v1/policies", headers=headers()).json()[0]["id"] == policy_id


def test_webhook_signature_and_workspace_isolation(client):
    connection_id = create_ready_connection(client, config={"webhook_secret": "hook-secret"})
    payload = {"id": "signed-1", "event_type": "repository.fork", "occurred_at": "2026-07-18T02:00:00Z", "actor": {"id": "a"}, "repository": {"name": "r"}}
    body = json.dumps(payload).encode()
    bad = client.post(f"/api/v1/webhooks/github/{connection_id}", headers={**headers(), "X-Hub-Signature-256": "sha256=bad"}, content=body)
    assert bad.status_code == 401
    signature = "sha256=" + hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    good = client.post(f"/api/v1/webhooks/github/{connection_id}", headers={**headers(), "X-Hub-Signature-256": signature}, content=body)
    assert good.status_code == 200
    assert client.get(f"/api/v1/connections/{connection_id}", headers={"X-Workspace-ID": "other"}).status_code == 404


def test_approval_mode_creates_and_resolves_approval(client):
    connection_id = create_ready_connection(client)
    action = client.post("/api/v1/actions", headers=headers(), json={"name": "Approval MFA", "action_type": "mfa", "mode": "approval", "provider": "idp"}).json()
    create_deployed_policy(client, connection_id, action["id"])
    payload = {"id": "approval-1", "event_type": "repository.clone", "occurred_at": "2026-07-18T03:00:00Z", "actor": {"id": "alice"}, "repository": {"name": "payments"}}
    client.post(f"/api/v1/webhooks/github/{connection_id}", headers=headers(), content=json.dumps(payload))
    approvals = client.get("/api/v1/approvals", headers=headers()).json()
    assert len(approvals) == 1 and approvals[0]["status"] == "pending"
    approved = client.post(f"/api/v1/approvals/{approvals[0]['id']}/approve?justification=Reviewed", headers=headers())
    assert approved.json()["status"] == "approved"
    assert main.repo.action_executions[approvals[0]["action_execution_id"]].status == "succeeded"


def test_dashboard_contract_returns_catalog_and_runtime_state(client):
    create_ready_connection(client)
    client.post("/api/v1/actions", headers=headers(), json={"name": "Escalate", "action_type": "escalate", "mode": "dry_run", "provider": "mailpit"})
    response = client.get("/api/v1/dashboard", headers={**headers(), "Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    dashboard = response.json()
    assert {item["key"] for item in dashboard["vendors"]} >= {"github", "gitlab", "generic-webhook"}
    github = next(item for item in dashboard["vendors"] if item["key"] == "github")
    assert github["status"] == "connected"
    assert dashboard["actions"][0]["mode"] == "Dry-run"
    assert set(dashboard["metrics"]) == {"events", "eventsDelta", "triggers", "triggerDelta", "latency", "latencyDelta"}
