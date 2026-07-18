from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .connectors import CONNECTORS, VENDORS
from .models import (
    ActionCreate, ActionDefinition, ActionExecution, ActionMode, ActionStatus, ActionType, Approval, AuditEvent, Check, CheckStatus, Connection, ConnectionCreate,
    ConnectionStatus, ConnectionTest, Evaluation, NormalizedEvent, Policy, PolicyDraft, PolicyDraftCreate, PolicyStatus, PolicyVersion,
)
from .policy import SafePolicyRuntime, generate_policy, run_test
from .repository import InMemoryRepository, SQLiteRepository


repo = SQLiteRepository(os.getenv("ACTIVITY_DB_PATH", "backend/data/activity.db"))
runtime = SafePolicyRuntime()
app = FastAPI(title="Activity Policy Control Plane", version="0.1.0")
cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
api = APIRouter(prefix="/api/v1")


@app.middleware("http")
async def persist_state(request: Request, call_next):
    response = await call_next(request)
    getattr(repo, "persist", lambda: None)()
    return response


@app.exception_handler(HTTPException)
async def api_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    code = detail.pop("code", "API_ERROR")
    message = detail.pop("message", "The request could not be completed.")
    correlation_id = request.headers.get("X-Correlation-ID", f"cor_{uuid4().hex}")
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": message, "details": detail, "correlation_id": correlation_id}})


def workspace(x_workspace_id: str | None = Header(default=None, alias="X-Workspace-ID")) -> str:
    return x_workspace_id or "default"


def actor(x_actor: str | None = Header(default=None, alias="X-Actor")) -> str:
    return x_actor or "api-user"


def audit(workspace_id: str, action: str, target_type: str, target_id: str, who: str = "system", after: dict[str, Any] | None = None, correlation_id: str | None = None) -> None:
    repo.audits.append(AuditEvent(workspace_id=workspace_id, action=action, target_type=target_type, target_id=target_id, actor=who, after=after, correlation_id=correlation_id))


def not_found(kind: str, item_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": f"{kind.upper()}_NOT_FOUND", "message": f"{kind} {item_id} was not found."})


def connection_or_404(workspace_id: str, connection_id: str) -> Connection:
    item = repo.find_connection(workspace_id, connection_id)
    if not item:
        raise not_found("connection", connection_id)
    return item


def _compact_count(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def _relative_time(value: datetime | None) -> str:
    if value is None:
        return "Never"
    seconds = max(0, int((datetime.now(timezone.utc) - value).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} hr ago"
    return f"{seconds // 86400} days ago"


def _enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _dashboard_data(workspace_id: str) -> dict[str, Any]:
    connections = [item for item in repo.connections.values() if item.workspace_id == workspace_id]
    policies = [item for item in repo.policies.values() if item.workspace_id == workspace_id]
    actions = [item for item in repo.actions.values() if item.workspace_id == workspace_id]
    events = [item for item in repo.events.values() if item.workspace_id == workspace_id]
    evaluations = [item for item in repo.evaluations.values() if item.workspace_id == workspace_id]
    audit_items = [item for item in repo.audits[::-1] if item.workspace_id == workspace_id][:8]
    colors = {"github": "#a78bfa", "gitlab": "#f97316", "generic-webhook": "#48a7ff"}
    icons = {"github": "GH", "gitlab": "GL", "generic-webhook": "GW"}
    descriptions = {
        "github": "Repository and organization activity",
        "gitlab": "Projects, repositories, and group activity",
        "generic-webhook": "Signed activity from a Git-compatible source",
    }
    vendor_cards: list[dict[str, Any]] = []
    for definition in VENDORS:
        connection = next((item for item in connections if item.vendor == definition.key), None)
        source_events = [item for item in events if item.vendor == definition.key]
        status = _enum_value(connection.status) if connection else "disabled"
        if status == "failed":
            status = "degraded"
        vendor_cards.append({
            "id": connection.id if connection else definition.key,
            "name": definition.display_name,
            "key": definition.key,
            "category": definition.category.replace("_", " ").title(),
            "description": descriptions.get(definition.key, "Vendor activity events"),
            "status": status,
            "events": _compact_count(len(source_events)),
            "lastEvent": _relative_time(max((item.received_at for item in source_events), default=None)),
            "icon": icons.get(definition.key, "V"),
            "color": colors.get(definition.key, "#a78bfa"),
            "capabilities": definition.capabilities,
            "checks": connection.last_test.checks if connection and connection.last_test else [],
            "remediation": connection.last_test.remediation if connection and connection.last_test else None,
            "eventLog": [item.model_dump(mode="json") for item in sorted(source_events, key=lambda event: event.received_at, reverse=True)[:20]],
        })
    policy_cards: list[dict[str, Any]] = []
    for policy in policies:
        policy_evaluations = [item for item in evaluations if item.policy_id == policy.id]
        matched = [item for item in policy_evaluations if item.decision.matched]
        policy_cards.append({
            "id": policy.id,
            "name": policy.name,
            "description": "Generated policy with immutable, test-backed version.",
            "version": f"v{policy.version}",
            "status": _enum_value(policy.status),
            "severity": _enum_value(policy.severity),
            "source": policy.vendor.title(),
            "evaluations": _compact_count(len(policy_evaluations)),
            "triggers": len(matched),
            "lastTrigger": _relative_time(max((item.evaluated_at for item in matched), default=None)),
            "latency": f"{round(sum(item.latency_ms for item in policy_evaluations) / len(policy_evaluations))} ms" if policy_evaluations else "—",
        })
    action_cards = [{
        "id": item.id,
        "name": item.name,
        "type": _enum_value(item.action_type).title() if _enum_value(item.action_type) != "mfa" else "MFA challenge",
        "provider": item.provider or "Configured provider",
        "mode": {"dry_run": "Dry-run", "approval": "Require approval", "automatic": "Automatic"}[_enum_value(item.mode)],
        "status": "active" if item.enabled else "paused",
        "executions": len([execution for execution in repo.action_executions.values() if execution.action_ref == item.id]),
        "color": {"allow": "#4ade80", "block": "#f87171", "mfa": "#4ade80", "escalate": "#a78bfa"}[_enum_value(item.action_type)],
    } for item in actions]
    activity = []
    for item in audit_items:
        title = item.action.replace(".", " ").replace("_", " ").title()
        activity.append({"id": item.id, "title": title, "detail": f"{item.target_type} · {item.target_id}", "time": _relative_time(item.created_at), "tone": "success", "icon": "check"})
    average_latency = round(sum(item.latency_ms for item in evaluations) / len(evaluations)) if evaluations else 0
    return {
        "demo": os.getenv("DEMO_MODE", "false").lower() in {"1", "true", "yes", "on"},
        "vendors": vendor_cards,
        "policies": policy_cards,
        "actions": action_cards,
        "activity": activity,
        "metrics": {"events": _compact_count(len(events)), "eventsDelta": "—", "triggers": str(sum(item.decision.matched for item in evaluations)), "triggerDelta": "—", "latency": f"{average_latency} ms" if evaluations else "—", "latencyDelta": "—"},
    }


@api.get("/vendors")
def vendors() -> list[Any]:
    return VENDORS


@api.get("/dashboard")
def dashboard(workspace_id: str = Depends(workspace)) -> dict[str, Any]:
    return _dashboard_data(workspace_id)


@api.get("/connections")
def connections(workspace_id: str = Depends(workspace)) -> list[Connection]:
    return repo.list_workspace(repo.connections, workspace_id)


@api.post("/connections", status_code=201)
def create_connection(payload: ConnectionCreate, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Connection:
    if payload.vendor not in CONNECTORS:
        raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_VENDOR", "message": f"Vendor {payload.vendor} is not supported."})
    if any(c.workspace_id == workspace_id and c.vendor == payload.vendor and c.name == payload.name for c in repo.connections.values()):
        raise HTTPException(status_code=409, detail={"code": "CONNECTION_EXISTS", "message": "A connection with this name already exists."})
    secret_metadata = {
        "reference": payload.secret_ref,
        "configured": bool(payload.secret_ref),
        "last_four": str(
            payload.config.get("token_last_four")
            or str(payload.config.get("personal_access_token") or payload.config.get("token") or "")[-4:]
        )[-4:]
        or None,
    }
    config = {
        key: value
        for key, value in payload.config.items()
        if key not in {"token", "personal_access_token", "access_token", "password", "webhook_secret"}
    }
    item = Connection(id=f"conn_{uuid4().hex}", workspace_id=workspace_id, vendor=payload.vendor, name=payload.name, status=ConnectionStatus.DRAFT, config=config, secret_ref=payload.secret_ref, secret_metadata=secret_metadata)
    repo.connections[item.id] = item
    connector = CONNECTORS[payload.vendor]
    repo.set_secret(payload.secret_ref, str(payload.config.get("personal_access_token") or payload.config.get("token") or "") or None)
    if hasattr(connector, "remember_token") and (token := repo.get_secret(payload.secret_ref)):
        connector.remember_token(item.id, token)
    if hasattr(connector, "remember_webhook_secret") and payload.config.get("webhook_secret"):
        connector.remember_webhook_secret(item.id, str(payload.config["webhook_secret"]))
    audit(workspace_id, "connection.created", "connection", item.id, who, {"vendor": item.vendor, "name": item.name})
    return item


@api.get("/connections/{connection_id}")
def get_connection(connection_id: str, workspace_id: str = Depends(workspace)) -> Connection:
    return connection_or_404(workspace_id, connection_id)


def _ingest_connector_events(connection: Connection, workspace_id: str, result: ConnectionTest) -> None:
    if result.status not in {"passed", "degraded"} or not hasattr(CONNECTORS[connection.vendor], "fetch_events"):
        return
    fetched_events = CONNECTORS[connection.vendor].fetch_events(connection)
    for event in fetched_events:
        if not repo.is_duplicate(workspace_id, event.dedupe_key):
            repo.events[event.event_id] = event
            evaluate_event(event)
    if fetched_events:
        connection.last_ingestion_at = max(event.received_at for event in fetched_events)


@api.post("/connections/{connection_id}/test")
def test_connection(connection_id: str, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Any:
    connection = connection_or_404(workspace_id, connection_id)
    connection.status = ConnectionStatus.TESTING
    result = CONNECTORS[connection.vendor].test_connection(connection)
    _ingest_connector_events(connection, workspace_id, result)
    connection.last_test = result
    connection.status = ConnectionStatus.CONNECTED if result.status == "passed" else (ConnectionStatus.FAILED if result.status == "failed" else ConnectionStatus.DEGRADED)
    connection.updated_at = datetime.now(timezone.utc)
    audit(workspace_id, "connection.tested", "connection", connection.id, who, {"status": result.status})
    return result


@api.post("/connections/{connection_id}/enable")
def enable_connection(connection_id: str, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Connection:
    connection = connection_or_404(workspace_id, connection_id)
    if not connection.last_test or connection.last_test.status != "passed":
        raise HTTPException(status_code=409, detail={"code": "CONNECTION_NOT_READY", "message": "Run a successful staged connection test before enabling ingestion."})
    connection.enabled = True
    connection.status = ConnectionStatus.CONNECTED
    connection.updated_at = datetime.now(timezone.utc)
    audit(workspace_id, "connection.enabled", "connection", connection.id, who, {"enabled": True})
    return connection


@api.post("/connections/{connection_id}/disable")
def disable_connection(connection_id: str, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Connection:
    connection = connection_or_404(workspace_id, connection_id)
    connection.enabled = False
    connection.status = ConnectionStatus.DISABLED
    connection.updated_at = datetime.now(timezone.utc)
    audit(workspace_id, "connection.disabled", "connection", connection.id, who, {"enabled": False})
    return connection


@api.get("/connections/{connection_id}/diagnostics")
def diagnostics(connection_id: str, workspace_id: str = Depends(workspace)) -> dict[str, Any]:
    connection = connection_or_404(workspace_id, connection_id)
    return {"connection_id": connection.id, "status": connection.status, "enabled": connection.enabled, "last_test": connection.last_test, "last_ingestion_at": connection.last_ingestion_at, "remediation": connection.last_test.remediation if connection.last_test else None}


@api.get("/connections/{connection_id}/events")
def connection_events(connection_id: str, workspace_id: str = Depends(workspace), limit: int = Query(default=50, ge=1, le=200), refresh: bool = False) -> list[NormalizedEvent]:
    connection = connection_or_404(workspace_id, connection_id)
    if refresh:
        connection.status = ConnectionStatus.TESTING
        result = CONNECTORS[connection.vendor].test_connection(connection)
        _ingest_connector_events(connection, workspace_id, result)
        connection.last_test = result
        connection.status = ConnectionStatus.CONNECTED if result.status == "passed" else (ConnectionStatus.FAILED if result.status == "failed" else ConnectionStatus.DEGRADED)
        connection.updated_at = datetime.now(timezone.utc)
    return [event for event in list(repo.events.values())[::-1] if event.workspace_id == workspace_id and event.connection_id == connection_id][:limit]


@api.post("/webhooks/{vendor}/{connection_id}")
async def webhook(vendor: str, connection_id: str, request: Request, workspace_id: str = Depends(workspace)) -> dict[str, Any]:
    connection = connection_or_404(workspace_id, connection_id)
    if vendor != connection.vendor:
        raise HTTPException(status_code=400, detail={"code": "VENDOR_MISMATCH", "message": "Webhook vendor does not match the connection."})
    body = await request.body()
    if not CONNECTORS[vendor].verify_webhook(dict(request.headers), body, connection):
        raise HTTPException(status_code=401, detail={"code": "INVALID_WEBHOOK_SIGNATURE", "message": "Webhook signature verification failed."})
    if not connection.enabled:
        raise HTTPException(status_code=409, detail={"code": "CONNECTION_DISABLED", "message": "Enable the connection before accepting events."})
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_EVENT", "message": "Webhook body must be JSON."}) from exc
    event = CONNECTORS[vendor].normalize(payload, connection, datetime.now(timezone.utc))
    duplicate = repo.is_duplicate(workspace_id, event.dedupe_key)
    if duplicate:
        return {"accepted": True, "duplicate": True, "event_id": event.event_id}
    repo.events[event.event_id] = event
    connection.last_ingestion_at = event.received_at
    evaluations = evaluate_event(event)
    return {"accepted": True, "duplicate": False, "event_id": event.event_id, "evaluations": [item.id for item in evaluations]}


@api.post("/policy-drafts", status_code=201)
def create_draft(payload: PolicyDraftCreate, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> PolicyDraft:
    draft = PolicyDraft(workspace_id=workspace_id, name=payload.name or "Suspicious activity policy", prompt=payload.prompt, vendor=payload.vendor, event_types=payload.event_types, timezone=payload.timezone, business_hours=payload.business_hours, exclusions=payload.exclusions, severity=payload.severity, action_ref=payload.action_ref, tags=payload.tags)
    repo.drafts[draft.id] = draft
    audit(workspace_id, "policy.prompt_submitted", "policy_draft", draft.id, who, {"name": draft.name})
    return draft


@api.post("/policy-drafts/{draft_id}/generate")
def generate_draft(draft_id: str, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> PolicyDraft:
    draft = repo.drafts.get(draft_id)
    if not draft or draft.workspace_id != workspace_id:
        raise not_found("policy draft", draft_id)
    draft.artifact = generate_policy(draft)
    draft.status = PolicyStatus.DRAFT
    draft.updated_at = datetime.now(timezone.utc)
    audit(workspace_id, "policy.version_generated", "policy_draft", draft.id, who, {"source_sha256": draft.artifact.source_sha256})
    return draft


@api.post("/policy-drafts/{draft_id}/test")
def test_draft(draft_id: str, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Any:
    draft = repo.drafts.get(draft_id)
    if not draft or draft.workspace_id != workspace_id:
        raise not_found("policy draft", draft_id)
    if not draft.artifact:
        raise HTTPException(status_code=409, detail={"code": "POLICY_NOT_GENERATED", "message": "Generate the policy artifact before testing it."})
    draft.latest_test_run = run_test(draft.artifact)
    draft.status = PolicyStatus.VALIDATED if draft.latest_test_run.status == "passed" else PolicyStatus.DRAFT
    draft.updated_at = datetime.now(timezone.utc)
    audit(workspace_id, "policy.test_run", "policy_draft", draft.id, who, {"status": draft.latest_test_run.status})
    return draft.latest_test_run


@api.get("/policy-drafts/{draft_id}")
def get_draft(draft_id: str, workspace_id: str = Depends(workspace)) -> PolicyDraft:
    draft = repo.drafts.get(draft_id)
    if not draft or draft.workspace_id != workspace_id:
        raise not_found("policy draft", draft_id)
    return draft


@api.post("/policy-drafts/{draft_id}/deploy", status_code=201)
def deploy_draft(draft_id: str, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> dict[str, Any]:
    draft = repo.drafts.get(draft_id)
    if not draft or draft.workspace_id != workspace_id:
        raise not_found("policy draft", draft_id)
    if not draft.artifact or not draft.latest_test_run or draft.latest_test_run.status != "passed":
        raise HTTPException(status_code=409, detail={"code": "POLICY_NOT_READY", "message": "All mandatory policy scenarios must pass before deployment."})
    policy_id = draft.policy_id or f"pol_{uuid4().hex}"
    version_number = max((p.version for p in repo.versions.values() if p.policy_id == policy_id), default=0) + 1
    version = PolicyVersion(policy_id=policy_id, version=version_number, workspace_id=workspace_id, artifact=draft.artifact)
    policy = repo.policies.get(policy_id) or Policy(id=policy_id, workspace_id=workspace_id, name=draft.name, vendor=draft.vendor, severity=draft.severity, tags=draft.tags, current_version_id=version.id, version=version_number)
    policy.current_version_id = version.id
    policy.version = version_number
    policy.status = PolicyStatus.ENABLED
    draft.policy_id = policy.id
    draft.status = PolicyStatus.ENABLED
    repo.versions[version.id] = version
    repo.policies[policy.id] = policy
    audit(workspace_id, "policy.deployed", "policy", policy.id, who, {"version": version_number, "source_sha256": version.artifact.source_sha256})
    return {"policy": policy, "version": version}


@api.get("/policies")
def policies(workspace_id: str = Depends(workspace), status: str | None = None, vendor: str | None = None) -> list[Policy]:
    result = repo.list_workspace(repo.policies, workspace_id)
    return [item for item in result if (not status or item.status == status) and (not vendor or item.vendor == vendor)]


@api.get("/policies/{policy_id}")
def get_policy(policy_id: str, workspace_id: str = Depends(workspace)) -> Policy:
    return policy_or_404(workspace_id, policy_id)


@api.get("/policies/{policy_id}/versions")
def policy_versions(policy_id: str, workspace_id: str = Depends(workspace)) -> list[PolicyVersion]:
    policy = repo.policies.get(policy_id)
    if not policy or policy.workspace_id != workspace_id:
        raise not_found("policy", policy_id)
    return sorted([item for item in repo.versions.values() if item.policy_id == policy_id], key=lambda item: item.version, reverse=True)


def policy_or_404(workspace_id: str, policy_id: str) -> Policy:
    policy = repo.policies.get(policy_id)
    if not policy or policy.workspace_id != workspace_id:
        raise not_found("policy", policy_id)
    return policy


@api.post("/policies/{policy_id}/enable")
def enable_policy(policy_id: str, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Policy:
    policy = policy_or_404(workspace_id, policy_id)
    policy.status = PolicyStatus.ENABLED
    audit(workspace_id, "policy.enabled", "policy", policy.id, who, {"status": policy.status})
    return policy


@api.post("/policies/{policy_id}/disable")
def disable_policy(policy_id: str, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Policy:
    policy = policy_or_404(workspace_id, policy_id)
    policy.status = PolicyStatus.DISABLED
    audit(workspace_id, "policy.disabled", "policy", policy.id, who, {"status": policy.status})
    return policy


@api.post("/policies/{policy_id}/rollback")
def rollback_policy(policy_id: str, version_id: str = Query(...), workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Policy:
    policy = policy_or_404(workspace_id, policy_id)
    version = repo.versions.get(version_id)
    if not version or version.policy_id != policy_id:
        raise not_found("policy version", version_id)
    policy.current_version_id = version.id
    policy.version = version.version
    policy.status = PolicyStatus.ENABLED
    audit(workspace_id, "policy.rollback", "policy", policy.id, who, {"version": version.version})
    return policy


def evaluate_event(event: NormalizedEvent) -> list[Evaluation]:
    results: list[Evaluation] = []
    for policy in repo.policies.values():
        if policy.workspace_id != event.workspace_id or policy.status != PolicyStatus.ENABLED or policy.vendor != event.vendor:
            continue
        version = repo.versions.get(policy.current_version_id)
        if not version or event.event_type not in version.artifact.required_event_types:
            continue
        started = time.perf_counter()
        decision = runtime.evaluate(version.artifact, event)
        evaluation = Evaluation(workspace_id=event.workspace_id, event_id=event.event_id, policy_id=policy.id, policy_version_id=version.id, vendor=event.vendor, decision=decision, latency_ms=round((time.perf_counter() - started) * 1000, 3))
        repo.evaluations[evaluation.id] = evaluation
        if decision.matched:
            execution = execute_action(evaluation, decision.action_ref or "allow")
            evaluation.action_execution_id = execution.id
        results.append(evaluation)
    return results


def execute_action(evaluation: Evaluation, action_ref: str) -> ActionExecution:
    action = repo.actions.get(action_ref)
    action_type = action.action_type if action else action_ref if action_ref in {"allow", "block", "mfa", "escalate"} else "allow"
    mode = action.mode if action else ActionMode.DRY_RUN
    key = f"{evaluation.workspace_id}:{evaluation.event_id}:{evaluation.policy_version_id}:{action_type}"
    existing = repo.action_by_idempotency(key)
    if existing:
        return existing
    if mode == ActionMode.APPROVAL:
        status = ActionStatus.PENDING
        result = {"message": "Awaiting authorized approval."}
    elif mode == ActionMode.DRY_RUN:
        status = ActionStatus.SUCCEEDED
        result = {"dry_run": True, "intended_action": action_type, "message": "No external system was changed."}
    else:
        status = ActionStatus.SUCCEEDED
        result = {"dry_run": False, "executed": True, "provider": action.provider if action else None}
    execution = ActionExecution(workspace_id=evaluation.workspace_id, evaluation_id=evaluation.id, action_ref=action_ref, action_type=action_type, mode=mode, status=status, idempotency_key=key, result=result)
    repo.record_action(execution)
    if status == ActionStatus.PENDING:
        approval = Approval(workspace_id=evaluation.workspace_id, action_execution_id=execution.id)
        repo.approvals[approval.id] = approval
    audit(evaluation.workspace_id, "action.executed", "action_execution", execution.id, after={"status": status, "action_type": action_type}, correlation_id=evaluation.correlation_id)
    return execution


@api.get("/evaluations")
def evaluations(workspace_id: str = Depends(workspace), policy_id: str | None = None, vendor: str | None = None, severity: str | None = None, matched: bool | None = None) -> list[Evaluation]:
    items = repo.list_workspace(repo.evaluations, workspace_id)
    return [item for item in items if (not policy_id or item.policy_id == policy_id) and (not vendor or item.vendor == vendor) and (not severity or item.decision.severity == severity) and (matched is None or item.decision.matched == matched)]


@api.get("/triggers/{trigger_id}")
def trigger(trigger_id: str, workspace_id: str = Depends(workspace)) -> dict[str, Any]:
    evaluation = repo.evaluations.get(trigger_id)
    if not evaluation or evaluation.workspace_id != workspace_id or not evaluation.decision.matched:
        raise not_found("trigger", trigger_id)
    return {"evaluation": evaluation, "event": repo.events.get(evaluation.event_id), "action": repo.action_executions.get(evaluation.action_execution_id) if evaluation.action_execution_id else None}


@api.get("/actions")
def actions(workspace_id: str = Depends(workspace)) -> list[ActionDefinition]:
    return repo.list_workspace(repo.actions, workspace_id)


@api.post("/actions", status_code=201)
def create_action(payload: ActionCreate, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> ActionDefinition:
    action = ActionDefinition(workspace_id=workspace_id, **payload.model_dump())
    repo.actions[action.id] = action
    audit(workspace_id, "action.created", "action", action.id, who, {"action_type": action.action_type, "mode": action.mode})
    return action


@api.post("/actions/{action_id}/test")
def test_action(action_id: str, workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> dict[str, Any]:
    action = repo.actions.get(action_id)
    if not action or action.workspace_id != workspace_id:
        raise not_found("action", action_id)
    audit(workspace_id, "action.tested", "action", action.id, who, {"dry_run": True})
    return {"action_id": action.id, "status": "succeeded", "dry_run": True, "intended_action": action.action_type, "message": "Action test does not contact an external provider."}


def approval_or_404(workspace_id: str, approval_id: str) -> Approval:
    approval = repo.approvals.get(approval_id)
    if not approval or approval.workspace_id != workspace_id:
        raise not_found("approval", approval_id)
    return approval


@api.post("/approvals/{approval_id}/approve")
def approve(approval_id: str, justification: str = Query(default="Approved by reviewer"), workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Approval:
    approval = approval_or_404(workspace_id, approval_id)
    approval.status, approval.justification, approval.decided_at = "approved", justification, datetime.now(timezone.utc)
    execution = repo.action_executions[approval.action_execution_id]
    execution.status = ActionStatus.SUCCEEDED
    execution.result = {"approved": True, "executed": True}
    audit(workspace_id, "action.approved", "approval", approval.id, who, {"status": approval.status})
    return approval


@api.post("/approvals/{approval_id}/reject")
def reject(approval_id: str, justification: str = Query(default="Rejected by reviewer"), workspace_id: str = Depends(workspace), who: str = Depends(actor)) -> Approval:
    approval = approval_or_404(workspace_id, approval_id)
    approval.status, approval.justification, approval.decided_at = "rejected", justification, datetime.now(timezone.utc)
    execution = repo.action_executions[approval.action_execution_id]
    execution.status = ActionStatus.FAILED
    execution.result = {"approved": False, "executed": False}
    audit(workspace_id, "action.rejected", "approval", approval.id, who, {"status": approval.status})
    return approval


@api.get("/audit-events")
def audit_events(workspace_id: str = Depends(workspace), target_type: str | None = None, action: str | None = None) -> list[AuditEvent]:
    return [item for item in repo.audits[::-1] if item.workspace_id == workspace_id and (not target_type or item.target_type == target_type) and (not action or item.action == action)]


@api.get("/approvals")
def approvals(workspace_id: str = Depends(workspace)) -> list[Approval]:
    return repo.list_workspace(repo.approvals, workspace_id)


@api.get("/policies/{policy_id}/stream")
def policy_stream(policy_id: str, workspace_id: str = Depends(workspace)) -> StreamingResponse:
    policy_or_404(workspace_id, policy_id)
    items = [item for item in repo.evaluations.values() if item.workspace_id == workspace_id and item.policy_id == policy_id]
    body = "".join(f"data: {json.dumps(item.model_dump(mode='json'))}\n\n" for item in items)
    return StreamingResponse(iter([body]), media_type="text/event-stream")


def seed_demo_data() -> None:
    """Seed a transparent, synthetic workspace so a fresh local demo is immediately usable."""
    if os.getenv("DEMO_MODE", "false").lower() not in {"1", "true", "yes", "on"} or repo.connections:
        return
    workspace_id = "default"
    connection = Connection(
        id="conn_demo_github", workspace_id=workspace_id, vendor="github", name="Acme Demo GitHub",
        status=ConnectionStatus.CONNECTED, enabled=True,
        config={"organization": "acme-demo", "demo_seed": True},
        secret_ref="openbao://demo/github", secret_metadata={"configured": True, "last_four": "demo"},
    )
    connection.last_test = ConnectionTest(status="passed", checks=[Check(name=name, status=CheckStatus.PASSED) for name in ["credentials", "api_reachability", "required_scopes", "event_subscription", "sample_event"]])
    connection.last_ingestion_at = datetime.now(timezone.utc)
    repo.connections[connection.id] = connection
    action = ActionDefinition(
        id="action_demo_escalate", workspace_id=workspace_id, name="Security escalation",
        action_type=ActionType.ESCALATE, mode=ActionMode.DRY_RUN, provider="Local demo notification",
        recipients=["security@example.invalid"], enabled=True,
    )
    repo.actions[action.id] = action
    draft = PolicyDraft(
        id="draft_demo_quiet_hours", workspace_id=workspace_id, name="After-hours repository access",
        prompt="Detect GitHub commit, clone, or fork activity between 01:00 and 05:00 and flag suspicious activity.",
        vendor="github", event_types=["repository.commit", "repository.clone", "repository.fork"],
        timezone="UTC", business_hours={}, exclusions={}, severity="high", action_ref=action.id,
    )
    draft.artifact = generate_policy(draft)
    draft.latest_test_run = run_test(draft.artifact)
    draft.status = PolicyStatus.ENABLED
    repo.drafts[draft.id] = draft
    version = PolicyVersion(id="version_demo_quiet_hours_v1", policy_id="policy_demo_quiet_hours", version=1, workspace_id=workspace_id, artifact=draft.artifact)
    policy = Policy(
        id="policy_demo_quiet_hours", workspace_id=workspace_id, name=draft.name, vendor="github",
        severity="high", tags=["demo", "after-hours"], current_version_id=version.id, version=1, status=PolicyStatus.ENABLED,
    )
    draft.policy_id = policy.id
    repo.versions[version.id] = version
    repo.policies[policy.id] = policy
    connector = CONNECTORS["github"]
    demo_payloads = [
        {"id": "demo-fork-01", "event_type": "repository.fork", "occurred_at": "2026-07-18T02:30:00Z", "actor": {"id": "alice", "login": "alice"}, "repository": {"id": "repo-1", "name": "payments", "organization": "acme-demo"}},
        {"id": "demo-commit-02", "event_type": "repository.commit", "occurred_at": "2026-07-18T10:15:00Z", "actor": {"id": "bob", "login": "bob"}, "repository": {"id": "repo-1", "name": "payments", "organization": "acme-demo"}},
        {"id": "demo-clone-03", "event_type": "repository.clone", "occurred_at": "2026-07-18T03:05:00Z", "actor": {"id": "automation-bot", "service_account": True}, "repository": {"id": "repo-2", "name": "infra", "organization": "acme-demo"}},
    ]
    for payload in demo_payloads:
        event = connector.normalize(payload, connection, datetime.now(timezone.utc))
        repo.events[event.event_id] = event
        evaluate_event(event)
    audit(workspace_id, "connection.enabled", "connection", connection.id, "demo-seed", {"demo": True})
    audit(workspace_id, "policy.deployed", "policy", policy.id, "demo-seed", {"version": 1, "demo": True})


seed_demo_data()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/livez")
def livez() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api)
