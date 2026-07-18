# Activity Policy Control Plane — Technical Specification

## 1. Scope and design principles

This specification defines the first production-oriented implementation for the product requirements in [PRODUCT_REQUIREMENTS.md](./PRODUCT_REQUIREMENTS.md).

Design principles:

1. Normalize vendor events once; policies should not contain provider-specific parsing.
2. Treat secrets, policy code, event data, decisions, and action results as separate security domains.
3. Make every asynchronous step observable and retryable.
4. Make policy versions immutable and decisions reproducible.
5. Prefer explicit capabilities and clear failure states over false “connected” or “protected” status.
6. Keep provider-specific behavior behind connector and action interfaces.

## 2. Open-source and free stack

The baseline implementation must be self-hostable and must not require a paid SaaS subscription or proprietary runtime. All components below have free/open-source community options. Production hosting, vendor API plans, email delivery, domains, and compute/storage are infrastructure costs outside the application stack.

| Layer | Choice | Reason |
|---|---|---|
| Web application | React + TypeScript + Vite + Tailwind CSS | Typed, responsive dashboard with a simple static build |
| API | Python + FastAPI | Matches generated Python policy model and supports async I/O |
| API data layer | SQLAlchemy + Alembic + Pydantic | Typed persistence, migrations, and request/schema validation |
| Agent orchestration | Python service using structured local-LLM output | Separates prompt-to-policy generation from request handling |
| Policy runtime | Python worker in an isolated sandbox | Executes the requested Python functions safely |
| Primary database | PostgreSQL | Relational lifecycle, audit, tenancy, and query consistency |
| Queue/event backbone | NATS JetStream | Open-source durable messaging, replay, consumer groups, and dead-letter subjects |
| Cache/rate limits | Valkey | Open-source in-memory cache and rate-limit store |
| Background workers | Python asyncio workers consuming NATS | Connector polling, tests, actions, and retries without a paid workflow service |
| Identity and SSO | Keycloak | Open-source OIDC/SAML, users, groups, and role mapping |
| Secrets | OpenBao | Open-source secret storage, rotation, access policies, and audit |
| Object storage | MinIO | Self-hosted S3-compatible storage for payloads and artifacts |
| Live updates | Server-sent events (SSE) | Simple one-way event stream for monitoring pages |
| Metrics/logs | OpenTelemetry + Prometheus + Grafana + Loki | Open-source traces, metrics, dashboards, and logs |
| Local AI | Ollama + an Apache-2.0-compatible open model | Runs the Policy Agent locally without a paid AI API |
| Packaging/deployment | Docker Compose, Docker Engine, and Kubernetes | Reproducible local setup and self-hosted production deployment |

The MVP can run as a modular monolith with separate worker processes. The interfaces below should still be implemented as modules so high-volume ingestion and policy execution can later be split into services. Before release, pin and review the exact license of every dependency and model selected; “free to use” must not be confused with permission to redistribute proprietary vendor SDKs or model weights.

## 3. Domain model

All tables have `id`, `workspace_id`, `created_at`, and `updated_at` unless stated otherwise. IDs are UUIDs. Timestamps are UTC.

### Workspace and identity

- `workspaces`: tenant boundary, name, status, retention configuration.
- `users`: identity provider subject, email, display name, status.
- `workspace_members`: workspace/user membership and role.
- `api_keys`: hashed API keys for automation, with scopes and expiry.

### Vendors and ingestion

- `vendor_definitions`: key, display name, category, supported auth/ingestion modes, capabilities.
- `vendor_connections`: workspace, vendor, name, status, configuration metadata, enabled flag, health timestamps.
- `secret_references`: secret manager path/version, purpose, redacted display metadata; never the secret value.
- `connection_capabilities`: required scopes, configured scopes, supported event types, diagnostics.
- `ingestion_cursors`: connection, source stream, cursor/watermark, last successful poll.
- `raw_events`: immutable payload pointer, source event ID, received time, checksum, retention state.
- `normalized_events`: canonical event fields, source reference, event type, actor/resource/time, dedupe key.

### Policies

- `policies`: stable policy identity, name, owner, severity, status, tags, description.
- `policy_versions`: version number, source prompt, generated code/object-storage URI, code hash, assumptions, SDK version, generated metadata.
- `policy_test_cases`: input fixture, expected decision, required flag, scenario type.
- `policy_test_runs`: version, runner version, status, started/finished timestamps, summary.
- `policy_test_results`: run, case, actual decision, trace, error, pass/fail.
- `policy_deployments`: version, target environment, deployment status, approval metadata, activated/deactivated times.

### Evaluation and actions

- `evaluation_runs`: normalized event, policy version, decision, reason, trace, latency, correlation ID.
- `policy_triggers`: evaluation run, severity, evidence pointer, acknowledgement state.
- `action_definitions`: workspace action configuration and secret references.
- `action_executions`: trigger/action, mode, status, idempotency key, provider request/result, attempts, timestamps.
- `approvals`: target type/id, requested by, reviewer, decision, justification, timestamps.
- `audit_events`: actor, action, target, before/after summary, correlation ID, IP/user agent if appropriate.

### Important indexes

- Unique `(workspace_id, vendor_id, name)` on connections.
- Unique `(workspace_id, source_vendor, source_event_id)` on normalized events where the vendor guarantees stable IDs.
- Unique `(workspace_id, dedupe_key)` on the dedupe window for webhook/poll duplicates.
- `(workspace_id, status, enabled)` on policies and connections.
- `(workspace_id, received_at DESC)` on normalized events.
- `(workspace_id, policy_version_id, evaluated_at DESC)` on evaluation runs.
- `(workspace_id, status, created_at)` on action executions and approvals.

## 4. Canonical event contract

Vendor adapters map source payloads into a versioned event envelope. Raw payloads remain available for evidence and future reprocessing.

```json
{
  "schema_version": "1.0",
  "event_id": "evt_01J...",
  "workspace_id": "ws_01J...",
  "connection_id": "conn_01J...",
  "vendor": "github",
  "event_type": "repository.fork",
  "occurred_at": "2026-07-18T01:42:17Z",
  "received_at": "2026-07-18T01:42:19Z",
  "actor": {
    "id": "user-123",
    "type": "human",
    "name": "alice",
    "email_hash": "sha256:...",
    "service_account": false
  },
  "resource": {
    "type": "repository",
    "id": "repo-123",
    "name": "payments",
    "organization": "acme"
  },
  "source": {
    "event_id": "github-delivery-123",
    "url": "https://github.example/...",
    "ip": "203.0.113.10",
    "user_agent": "github-hookshot/..."
  },
  "attributes": {
    "action": "fork",
    "visibility": "private"
  },
  "raw_payload_ref": "s3://events/...",
  "dedupe_key": "github:github-delivery-123"
}
```

Rules:

- `event_type` uses a controlled namespaced vocabulary such as `repository.fork` or `identity.login`.
- Missing fields are null, never fabricated.
- Vendor timestamps and ingestion timestamps are both retained.
- PII is minimized. Email addresses should be hashed or encrypted according to workspace policy.
- A connector must report `unsupported`, `partial`, or `complete` normalization status.

## 5. Connector contract

Every connector implements the same interface:

```python
class Connector(Protocol):
    def validate_config(self, config: dict) -> ValidationResult: ...
    def test_connection(self, credentials: SecretRef, config: dict) -> ConnectionTest: ...
    def capabilities(self, config: dict) -> ConnectorCapabilities: ...
    def subscribe(self, config: dict) -> SubscriptionResult: ...
    def poll(self, cursor: str | None, config: dict) -> PollResult: ...
    def verify_webhook(self, headers: dict, body: bytes, secret: SecretRef) -> bool: ...
    def normalize(self, payload: dict, metadata: SourceMetadata) -> list[NormalizedEvent]: ...
    def remediation(self, diagnostic: Diagnostic) -> RemediationGuide: ...
```

Connectors may use webhooks, polling, or both. Webhooks must verify signatures before queueing. Pollers must honor provider rate limits and persist cursors transactionally with accepted events.

### Connection test stages

The API returns a structured result rather than one boolean:

```json
{
  "status": "degraded",
  "checks": [
    {"name": "credentials", "status": "passed"},
    {"name": "api_reachability", "status": "passed"},
    {"name": "required_scopes", "status": "failed", "code": "MISSING_AUDIT_SCOPE"},
    {"name": "event_subscription", "status": "skipped"},
    {"name": "sample_event", "status": "not_available"}
  ],
  "remediation": {
    "summary": "Grant organization audit-log access and perform a test fork event.",
    "steps": ["..."],
    "test_actions": ["Fork a non-production test repository."]
  }
}
```

## 6. Policy contract and sandbox

### Policy artifact

A policy version stores:

- Generated source code and SHA-256 hash.
- Prompt and structured policy intent.
- Required event types and fields.
- Severity and default action reference.
- Test fixtures and expected results.
- Generator model/version and policy SDK version.
- Creation, review, approval, and deployment metadata.

### Runtime interface

```python
@dataclass(frozen=True)
class PolicyDecision:
    matched: bool
    severity: Literal["low", "medium", "high", "critical"]
    reason_code: str
    explanation: str
    evidence: dict[str, str]
    action_ref: str | None = None

def evaluate(event: NormalizedEvent, context: PolicyContext) -> PolicyDecision:
    ...
```

The runtime should:

- Execute a pinned artifact in a short-lived worker/container.
- Enforce CPU, memory, execution-time, output-size, and recursion limits.
- Use a restricted Python interpreter or sandbox boundary with an import allowlist.
- Deny sockets, subprocesses, filesystem writes, environment-variable reads, dynamic code generation, and access to application credentials.
- Provide only immutable event/context objects and approved pure helper functions.
- Kill a worker on timeout and emit an evaluation error rather than silently treating the event as safe.
- Record a bounded explanation/trace; never store secrets in traces.

The generated function is not trusted merely because it was produced by the agent. Every artifact must pass static validation, test execution, and deployment authorization.

### Agent generation protocol

The model must return structured JSON validated against a schema:

- `policy_name`
- `summary`
- `intent`
- `required_event_types`
- `required_fields`
- `assumptions`
- `severity`
- `action_ref`
- `python_source`
- `test_cases`

If output is invalid, the service retries with a repair prompt and then returns a user-visible generation error. The model must not be allowed to call vendor APIs directly.

## 7. API specification

All endpoints are under `/api/v1`, require workspace authorization, and return a request/correlation ID.

### Vendors

- `GET /vendors` — list vendor definitions and capabilities.
- `GET /connections` — list workspace connections.
- `POST /connections` — create a connection with secret references.
- `GET /connections/{id}` — retrieve redacted connection detail.
- `POST /connections/{id}/test` — run staged connection test.
- `POST /connections/{id}/enable` — enable ingestion.
- `POST /connections/{id}/disable` — disable ingestion.
- `GET /connections/{id}/diagnostics` — retrieve health and remediation guidance.
- `GET /connections/{id}/events` — query recent normalized events.
- `POST /webhooks/{vendor}/{connection_id}` — receive signed vendor events.

### Policy Agent and policies

- `POST /policy-drafts` — create a draft from prompt and source selection.
- `POST /policy-drafts/{id}/generate` — generate/repair policy artifact.
- `POST /policy-drafts/{id}/test` — run mandatory and custom test cases.
- `GET /policy-drafts/{id}` — retrieve prompt, source, artifact, assumptions, and results.
- `POST /policy-drafts/{id}/deploy` — validate readiness and create deployment.
- `GET /policies` — list policy identities and current versions.
- `GET /policies/{id}/versions` — list immutable versions.
- `POST /policies/{id}/enable` and `POST /policies/{id}/disable` — lifecycle controls.
- `POST /policies/{id}/rollback` — activate a previous validated version.

### Monitoring and actions

- `GET /evaluations` — filter decisions by time, policy, vendor, severity, and result.
- `GET /policies/{id}/stream` — SSE stream for monitoring updates.
- `GET /triggers/{id}` — evidence and action history.
- `GET /actions` — list action definitions.
- `POST /actions` — create an action definition.
- `POST /actions/{id}/test` — test an action in dry-run mode.
- `POST /approvals/{id}/approve` and `POST /approvals/{id}/reject` — approval workflow.
- `GET /audit-events` — filterable audit history.

### Error format

```json
{
  "error": {
    "code": "CONNECTION_MISSING_SCOPE",
    "message": "The connection is authenticated but cannot read organization audit events.",
    "details": {"required_scope": "audit:read"},
    "correlation_id": "cor_01J..."
  }
}
```

## 8. Event processing semantics

1. Receive webhook or poll provider API.
2. Authenticate the source and validate payload size/schema.
3. Persist a raw payload reference and source metadata.
4. Derive a dedupe key and ignore a duplicate while retaining a duplicate metric.
5. Normalize the payload and publish `event.accepted` or `event.normalization_failed`.
6. Route the normalized event to policies by workspace, vendor, and event type.
7. Evaluate each enabled policy with a bounded timeout.
8. Persist the decision and evidence before submitting an action.
9. Submit action jobs with idempotency key `workspace:event:policy_version:action`.
10. Persist action outcome and publish monitoring/audit updates.

At-least-once delivery is expected. Correctness comes from dedupe keys, immutable decisions, and idempotent actions. If policy execution fails, the decision is `evaluation_error`; it is never silently converted to allow.

## 9. Security requirements

- Enforce tenant/workspace scoping in the service layer and database queries.
- Use OIDC/SAML SSO in enterprise deployments; local auth only for development.
- Use short-lived access tokens and refresh-token rotation.
- Store only secret references in PostgreSQL; secret values belong in OpenBao or an equivalent self-hosted secret system.
- Redact tokens, cookies, authorization headers, and sensitive payload fields in logs and traces.
- Validate webhook signatures and reject replayed deliveries where provider support exists.
- Apply per-user and per-connection rate limits.
- Use separate service identities for API, connector workers, policy workers, and action workers.
- Require approval for high-risk actions by default.
- Scan generated policy source for unsafe AST nodes before runtime execution.
- Keep raw events and evidence encrypted with workspace-specific access controls.
- Add export/delete controls to meet retention and privacy requirements.

## 10. Reliability and operations

### Retry policy

Retries use exponential backoff with jitter and a dead-letter queue. Retryable failures include provider timeouts, 429s, and transient database errors. Authentication errors, invalid signatures, unsupported events, and policy validation errors are non-retryable until configuration changes.

### Backpressure

- Webhook endpoint acknowledges only after durable queue acceptance.
- Pollers slow down on provider rate-limit responses.
- Evaluation workers scale on queue age and depth.
- Action workers have separate concurrency limits per vendor/control.
- The UI shows stale data indicators when queue lag exceeds the target.

### Observability

Every request, event, evaluation, and action carries a correlation ID. Minimum metrics:

- Connector success/failure by vendor and check stage.
- Events received, rejected, duplicated, normalized, and unsupported.
- Queue depth and oldest message age.
- Policy evaluation count, match rate, error rate, and p50/p95 latency.
- Action success/failure/retry/approval latency.
- SSE subscriber count and delivery lag.

Alerts should cover connector failure, sustained normalization failures, evaluation errors, queue backlog, action failures, and secret expiry.

## 11. Testing strategy

- Unit tests for connector validation, normalization, dedupe, policy helpers, permissions, and action idempotency.
- Contract tests against recorded vendor fixtures and webhook signature examples.
- Policy test runner tests for positive, negative, boundary, malformed, and duplicate events.
- Integration tests for database, queue, secret references, and SSE updates.
- Security tests for tenant isolation, role enforcement, secret redaction, sandbox escapes, and webhook replay.
- Load tests for ingestion and evaluation throughput.
- Failure tests for worker termination, provider timeout, queue retry, duplicate delivery, and action retry.
- Browser-level tests for the four primary sidebar workflows.

## 12. Definition of done for a policy

A policy version is deployable only when:

- Its source is valid, hashed, and compatible with the runtime SDK.
- Static safety checks pass.
- All mandatory test cases pass.
- Required event fields are available from the selected connections.
- Action configuration exists and is authorized for the workspace.
- Required approval, if any, is complete.
- An audit event and immutable version record are written.
