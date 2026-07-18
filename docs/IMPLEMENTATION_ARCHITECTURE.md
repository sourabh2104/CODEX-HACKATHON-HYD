# Activity Policy Control Plane — Implementation Architecture

## 1. Architecture overview

The recommended implementation starts as a modular monolith plus workers. This is simpler to deploy for the first vertical slice while preserving the boundaries needed to scale ingestion, policy execution, and action delivery independently. The baseline is fully self-hostable with open-source/free community software; paid cloud services are optional deployment choices, not application dependencies.

```text
                           +-----------------------+
                           | React / Vite UI       |
                           | Dashboard + SSE       |
                           +-----------+-----------+
                                       |
                               HTTPS / OIDC
                                       |
                           +-----------v-----------+
                           | API / Control Plane   |
                           | FastAPI, RBAC, CRUD,  |
                           | policy lifecycle      |
                           +---+-------+-------+---+
                               |       |       |
                 +-------------+       |       +----------------+
                 |                     |                        |
       +---------v---------+  +--------v---------+    +---------v---------+
       | Connector Manager |  | Policy Agent     |    | Action Manager    |
       | webhooks/pollers  |  | prompt -> draft  |    | allow/block/MFA/  |
       | tests/diagnostics |  | tests/revisions  |    | escalate/approval |
       +---------+---------+  +--------+---------+    +---------+---------+
                 |                     |                        |
                 +----------+----------+------------------------+
                            |
                     +------v------+
                     | NATS         |
                     | JetStream    |
                     +--+-------+---+
                        |       |
          +-------------+       +----------------+
          |                                       |
  +-------v--------+                     +--------v--------+
  | Normalizer     |                     | Policy Runtime  |
  | raw -> canonical|                    | isolated workers |
  +-------+--------+                     +--------+--------+
          |                                       |
          +------------------+--------------------+
                             |
                    +--------v---------+
                    | Evaluation /     |
                    | Decision Service |
                    +----+--------+----+
                         |        |
                 +-------v--+  +--v-------------+
                 | Postgres |  | Object storage |
                 | state    |  | raw/evidence   |
                 +----------+  +----------------+

 External systems: GitHub, GitLab, AWS, Azure, GCP, Jira, Trello, identity providers, email/SIEM.
```

## 2. Logical components

### Web application

Owns layout, navigation, forms, policy editor, test result presentation, live monitoring, accessibility, and optimistic status updates. It does not hold vendor credentials or execute policy code.

Core routes:

```text
/dashboard
/vendors
/vendors/:connectionId
/policy-agent
/policy-agent/:draftId
/deployed-policies
/deployed-policies/:policyId
/deployed-policies/:policyId/monitor
/actions
/audit
```

### API/control plane

Owns authentication, workspace authorization, resource lifecycle, validation, audit writes, deployment orchestration, and SSE subscriptions. It should remain stateless so multiple instances can run behind a load balancer.

### Connector manager

Owns vendor definitions, credentials references, test connection checks, webhook endpoints, poll scheduling, cursors, rate limiting, and remediation guides. A connector adapter must not directly write policy decisions.

### Policy Agent

Owns prompt intake, structured generation, policy-source validation, scenario generation, revision loop, and human-readable explanations. It may use an LLM provider through a narrow adapter. It does not receive raw secret values or call vendor APIs.

### Policy runtime

Owns static validation and evaluation of immutable policy artifacts. It receives only the normalized event, policy context, and approved helper library. It returns a bounded `PolicyDecision`.

### Evaluation service

Owns routing events to enabled policies, invoking the runtime, persisting decisions, and publishing trigger events. It should support horizontal workers partitioned by workspace or event stream.

### Action manager

Owns action definitions, approval checks, idempotency, provider control adapters, retries, notification templates, and action results. Action adapters expose capabilities so a policy cannot select a block operation a vendor does not support.

### Persistence and event infrastructure

PostgreSQL is the source of truth for control-plane state and decisions. The queue/bus provides durable handoff between stages. Object storage holds large immutable raw payloads, generated source, and evidence bundles.

## 3. Repository/module layout

The following layout is suitable for a Python backend and TypeScript frontend:

```text
apps/
  web/
    app/                 # route-level pages
    components/          # shared UI
    features/            # vendors, policy-agent, policies, actions
    lib/                 # API client, auth, SSE client
  api/
    app/
      api/               # FastAPI routers and dependencies
      domain/            # entities, value objects, policies
      services/          # use cases and orchestration
      repositories/      # database access
      connectors/        # GitHub, GitLab, AWS, Jira adapters
      policy_agent/      # generation and test scenario services
      policy_runtime/    # validator, sandbox client, SDK
      actions/           # action adapters and retry logic
      workers/           # queue consumers and schedulers
      security/          # auth, RBAC, secret references, redaction
      observability/     # tracing, metrics, structured logs
      migrations/
packages/
  event-contracts/      # versioned JSON/Python/TypeScript schemas
  policy-sdk/            # approved pure policy helpers
  connector-contracts/   # adapter interfaces and fixtures
infra/
  docker/
  k8s/
  terraform/
docs/
```

The exact framework can change, but domain modules should not import UI code, vendor SDKs should stay inside connectors, and policy runtime code should not share process credentials with the API.

## 4. Asynchronous workflows

### 4.1 Webhook ingestion

```text
Vendor webhook
   -> API signature verification
   -> durable raw-event write
   -> event.accepted message
   -> normalization worker
   -> event.normalized message
   -> evaluation worker
   -> decision.persisted message
   -> action worker
   -> action.completed message
   -> SSE + audit consumers
```

The webhook response should be fast and independent of policy execution. If the payload is accepted durably, return success; downstream processing is observable through the connection page.

### 4.2 Polling ingestion

The scheduler creates a poll job per enabled connection. The worker:

1. Loads the last cursor.
2. Calls the provider with the configured time/rate window.
3. Writes raw events and the next cursor in one database transaction.
4. Publishes accepted events.
5. Records provider rate limits and latency.

If a poll fails, retain the previous cursor. The next run retries the same window with bounded overlap, relying on dedupe to prevent duplicates.

### 4.3 Policy creation

```text
Prompt + source selection
   -> intent extraction
   -> structured policy generation
   -> AST/static validation
   -> scenario generation
   -> isolated test runner
   -> results
       -> all pass: Ready to deploy
       -> failure: revision context -> generation/test loop
```

The agent should stop after a configured number of automated revisions and explain what remains unresolved. It must not claim readiness when a required field cannot be sourced.

### 4.4 Deployment

```text
Deploy request
   -> RBAC/approval check
   -> readiness validation
   -> persist immutable policy version
   -> register event-type subscriptions
   -> activate deployment
   -> audit + monitoring update
```

Deployment is idempotent by policy version and target environment. A failed activation must leave the prior active version unchanged.

### 4.5 Trigger and response

```text
Normalized event
   -> matching policy index
   -> isolated evaluation
   -> decision + evidence persisted
   -> action mode check
      -> dry-run: record only
      -> approval: create approval task
      -> automatic: execute adapter
   -> result, audit, notification, live stream
```

Persisting the decision before action execution is required. This allows a failed action to be retried without reevaluating the event or losing the original evidence.

## 5. Deployment topology

### Development

Docker Compose can provide:

- Web application.
- API.
- Worker process.
- PostgreSQL.
- NATS JetStream.
- Valkey.
- Keycloak.
- OpenBao.
- MinIO.
- Ollama with a locally downloaded open model.
- Local object-storage emulator.

Vendor webhooks can use a secure tunnel only in local development. Development credentials must be separate from production and must never be committed.

### Production

Recommended minimum topology:

- Two or more stateless web/API replicas.
- Dedicated connector worker pool.
- Dedicated policy runtime worker pool with stronger isolation.
- Dedicated action worker pool with low concurrency and egress allowlists.
- PostgreSQL with backups and point-in-time recovery.
- NATS JetStream with dead-letter subjects and durable consumers.
- MinIO with encryption and lifecycle policies.
- OpenBao with separate paths and identities per workspace/environment.
- Load balancer/API gateway with TLS, WAF, rate limits, and webhook routing.

Kubernetes is appropriate when the organization already operates it; Docker Compose is sufficient for a small single-host deployment. The policy runtime should run in a separate node pool or sandboxed job class from the API.

## 6. Data flow and trust boundaries

```text
TB1: Browser -> API
     OIDC token, CSRF protection, TLS, RBAC

TB2: API -> Secret manager
     Secret references only; no secret values in database

TB3: Vendor -> Ingestion edge
     Signature verification, payload limits, replay controls

TB4: Queue -> Workers
     Authenticated producer/consumer, durable messages, tenant metadata

TB5: Policy runtime
     Untrusted generated code, isolated process/container, no network/secrets

TB6: Action worker -> External control
     Egress allowlist, scoped credentials, idempotency, approval gates
```

Every boundary must attach `workspace_id` and `correlation_id`. A message without either is rejected and counted as a security/contract error.

## 7. Authorization model

Authorization is enforced at three levels:

1. Route-level permission: can the role call the endpoint?
2. Resource-level scope: does the resource belong to the workspace and permitted project/environment?
3. Operation-level guard: is the requested transition valid, approved, and allowed for the resource?

Example: an Engineer may create a policy and enable a low-risk policy, but deployment of a critical policy may require Administrator approval. The policy service, not only the frontend, must enforce this.

## 8. Failure handling and recovery

| Failure | User-visible state | Recovery |
|---|---|---|
| Invalid vendor credentials | Failed connection with provider error | Update credentials and re-test |
| Missing vendor scope | Degraded connection with exact scope/remediation | Grant scope and re-test |
| No source activity | Connected, no events with test-event guidance | Perform suggested activity or change window |
| Unsupported event | Normalization warning | Configure supported event or connector enhancement |
| Queue backlog | Stale/lagging monitoring banner | Scale workers or investigate provider/queue |
| Policy timeout | Evaluation error; no silent allow | Inspect policy/runtime and retry/revise |
| Action provider failure | Triggered, action failed | Retry idempotently or use manual fallback |
| Approval rejected | Triggered, action rejected | Record justification; no automatic retry |
| Worker crash | Pending job remains recoverable | Queue redelivery and idempotency handling |

Recovery procedures should be documented as runbooks before production launch: replay a time range, rotate a vendor credential, disable a policy, drain a connector, re-drive a dead-letter job, and restore a database backup.

## 9. Phased implementation plan

### Phase 0 — foundation

- Repository layout, CI, local Compose environment.
- Authentication, workspace model, RBAC, audit event helper.
- PostgreSQL migrations and queue abstraction.
- Event contract package and redaction utilities.

### Phase 1 — GitHub vertical slice

- GitHub webhook connector and staged connection test.
- Raw/normalized event persistence and recent-event view.
- Policy Agent prompt flow and structured generated Python artifact.
- Static validation and isolated test runner.
- Ready-to-deploy lifecycle and policy list.

### Phase 2 — monitoring and actions

- Evaluation routing and live SSE monitoring.
- Allow and escalate actions.
- Dry-run, retries, idempotency, email templates, trigger detail.
- Audit search and operational metrics.

### Phase 3 — enterprise controls

- Approval workflow, rollback, historical replay, block/MFA adapters.
- GitLab, Jira, and AWS connectors.
- SSO/SCIM, retention controls, evidence export, rate-limit dashboards.

## 10. Build checklist

- [ ] Define and version canonical event schemas.
- [ ] Implement workspace-scoped repositories and permission tests.
- [ ] Implement GitHub connector with webhook verification and sample-event diagnostics.
- [ ] Implement secret-manager adapter and redaction middleware.
- [ ] Implement policy generation schema and AST validator.
- [ ] Implement isolated policy test/evaluation worker.
- [ ] Implement immutable policy versions and readiness validation.
- [ ] Implement event routing, decision persistence, and SSE monitoring.
- [ ] Implement idempotent allow/escalate actions and dry-run mode.
- [ ] Add connection, policy, evaluation, action, and audit screens.
- [ ] Add metrics, tracing, dead-letter handling, and operational alerts.
- [ ] Run tenant isolation, sandbox escape, webhook replay, and failure-recovery tests.
