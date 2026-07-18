# Activity Policy Control Plane

## 1. Product summary

Activity Policy Control Plane is a security operations application that connects to business and infrastructure vendors, collects their activity events, evaluates those events against user-defined policies, and takes a controlled response when a policy is triggered.

The product turns a plain-language risk scenario into a testable Python policy, shows the evidence used to validate it, and provides a clear deployment and monitoring lifecycle:

```text
Connect vendor -> Ingest events -> Describe risk -> Generate policy -> Test -> Deploy -> Monitor -> Respond
```

The first release is intended for security engineers, platform engineers, and administrators who need organization-wide visibility and guardrails without writing every detection rule from scratch.

## 2. Goals and non-goals

### Goals

- Provide one dashboard for vendor connections, policies, deployed policies, and responses.
- Support common event sources through an extensible connector model.
- Let a user describe a threat or risk scenario in natural language.
- Generate a human-readable Python policy function with an explanation of its assumptions.
- Generate positive, negative, boundary, and malformed test scenarios and show their results.
- Require all policy scenarios to pass before a policy can be deployed.
- Evaluate normalized events in near real time and retain an auditable decision trail.
- Allow a policy to be enabled, disabled, monitored, and rolled back without code changes.
- Make missing vendor permissions and missing event activity understandable to the user.
- Provide safe response actions: allow, block, MFA challenge, and escalation.

### Non-goals for the first release

- Replacing a full SIEM, SOAR, IAM, or ticketing platform.
- Arbitrary code execution inside the application process.
- Automatically changing vendor permissions without explicit user approval.
- Guaranteeing that every vendor exposes every requested event type.
- Making irreversible blocking decisions without a configured action policy and audit record.

## 3. Personas

| Persona | Need | Primary areas |
|---|---|---|
| Security engineer | Create detections and responses for suspicious activity | Policy Agent, Deployed Policies, Actions |
| Platform engineer | Connect Git, cloud, and project systems and troubleshoot ingestion | Vendors, monitoring |
| Security administrator | Control who can deploy or change policies | Dashboard, policy approvals, audit |
| Auditor | Prove what was connected, detected, and acted upon | Audit trail, policy evidence, action history |
| Incident responder | Investigate a trigger and act quickly | Live monitoring, event detail, Actions |

## 4. Information architecture

The authenticated application has four persistent sidebar areas:

1. **Vendors** — configure, test, enable, disable, and inspect vendor connections.
2. **Policy Agent** — describe a scenario, generate a policy, test it, revise it, and prepare it for deployment.
3. **Deployed Policies** — manage deployed policy versions and inspect live evaluation evidence.
4. **Actions** — configure responses, escalation destinations, approvals, and action history.

The global header should include workspace selector, search, notifications, current user, and a connection/event health indicator.

## 5. Functional requirements

### 5.1 Dashboard

The dashboard is the operational landing page. It must show:

- Number of connected, disabled, degraded, and failing vendors.
- Events received in the selected time range.
- Policies enabled, disabled, deploying, and failing evaluation.
- Policy triggers by severity and vendor.
- Pending approvals and failed actions.
- A recent activity feed with links to the source event, policy version, and action result.
- A system health banner when ingestion latency, queue backlog, or connector failures exceed thresholds.

The dashboard must use the same permission checks as the detailed pages; summary cards must never expose data a user cannot access.

### 5.2 Vendors

#### Vendor catalog

The initial catalog should include:

- Version control: GitHub, GitLab, and generic Git webhook.
- Cloud: AWS CloudTrail, Azure Activity Log, and Google Cloud Audit Logs.
- Project management: Jira and Trello.
- Identity and collaboration candidates: Okta, Microsoft Entra ID, Slack, and Google Workspace.

Connectors are capability-driven. A vendor entry must declare supported authentication methods, event types, ingestion modes, required permissions, rate limits, and test instructions.

#### Connection lifecycle

Each connection has one of these states:

```text
Draft -> Testing -> Connected -> Degraded
                    |             |
                    +-> Failed <--+
Connected/Degraded -> Disabled -> Testing
```

The user flow is:

1. Select a vendor and connection type.
2. Enter the required credentials and configuration.
3. Save the configuration as encrypted secret references.
4. Select **Test connection**.
5. Show a step-by-step result: authentication, permission check, API reachability, event capability, and sample event retrieval.
6. If successful, allow the user to enable ingestion.
7. Show recent events and the last successful ingestion timestamp.

Example GitHub fields:

- Connection name.
- Organization name.
- Organization URL.
- GitHub API URL (defaulted, editable for enterprise installations).
- Personal access token or OAuth installation.
- Requested event types.
- Webhook secret, if webhook mode is selected.
- Initial backfill window, with a safe default and a maximum limit.

The UI must never display the full token after saving. It should show only provider, owner, last four characters where appropriate, creation time, expiry time if available, and last rotation time.

#### Connection diagnostics

A successful authentication does not imply that useful events are available. The connection detail page must distinguish:

- Authentication failed.
- API reachable but token lacks a required scope.
- Scope is valid but the organization/project has no activity in the selected window.
- Webhook is configured but has not delivered an event.
- Events are arriving but cannot be normalized.
- Events are arriving and being evaluated.

When activity is absent, the page must provide:

- The exact missing permission or capability when the vendor API reports it.
- The action the user must take, such as enable audit log access, install an organization webhook, grant repository read access, or enable CloudTrail data events.
- The exact activity to perform to produce a test event, such as create a test repository branch, clone a repository, fork a repository, update a Jira issue, or perform a cloud console login.
- A **Generate test event instructions** action and a **Re-test** action.

Users can enable or disable ingestion. Disabling stops new ingestion and policy evaluation but preserves connection configuration, historical events, and audit data according to retention settings.

### 5.3 Policy Agent

The Policy Agent is a guided creation workspace rather than a free-form code editor.

#### Policy creation inputs

- Natural-language prompt describing the threat or risk scenario.
- Event sources and event types to inspect.
- Severity: low, medium, high, or critical.
- Time zone and business-hours definition.
- Optional exclusions for service accounts, repositories, IP ranges, users, or environments.
- Desired response action.
- Policy name, owner, and tags.

Example prompt:

> Detect GitHub commit, clone, or fork activity performed between 01:00 and 05:00 in the organization time zone. Flag it as suspicious unless the actor is an approved automation account.

#### Agent output

The agent must produce:

- A policy summary in plain language.
- The generated Python function and policy metadata.
- Assumptions and ambiguities, including time zone and event coverage.
- Required normalized fields.
- A list of test scenarios.
- Recommended severity and action, which the user can change.
- A confidence/coverage warning when the selected vendors cannot produce all required evidence.

Generated policies must follow a stable interface:

```python
def evaluate(event: NormalizedEvent, context: PolicyContext) -> PolicyDecision:
    """Return a decision for one normalized event."""
```

The function must be deterministic for the same event and context. It may use only the approved policy SDK and must not perform network calls, filesystem access, subprocess execution, imports outside the allowlist, or secret access.

#### Test and revision loop

The agent creates at least:

- A matching event that must trigger.
- A non-matching event that must not trigger.
- Boundary events immediately before and after the threshold.
- Events from excluded actors or resources.
- A malformed or incomplete event.
- A duplicate event to verify idempotency behavior.

The test view shows input event, expected outcome, actual outcome, explanation, and policy trace fields. A policy cannot become deployable until all mandatory scenarios pass. If a scenario fails, the user can revise the prompt, adjust assumptions, edit the policy in an advanced view, or add a test case and regenerate.

The UI must clearly label agent-generated content as a draft until reviewed by a user.

#### Readiness and deployment

When all mandatory scenarios pass, the page shows **Ready to deploy**. Clicking it creates an immutable policy version and starts the deployment workflow. Deployment must record:

- Author and approver.
- Source prompt and generated code hash.
- Test suite and results.
- Selected event sources.
- Requested action behavior.
- Deployment timestamp and target environment.

If the workspace requires approval, Ready to deploy creates a pending approval instead of enabling the policy.

### 5.4 Deployed Policies

The list must support filtering by status, vendor, severity, owner, tag, and last trigger. Each row shows name, version, status, event sources, last evaluation, trigger count, and last action result.

Supported lifecycle states:

```text
Draft -> Validated -> Pending approval -> Deploying -> Enabled
                                      |              |
                                      +-> Rejected   +-> Disabled
                                                     |
                                                     +-> Retired
```

Users can:

- Enable or disable a policy.
- Start or stop monitoring.
- View versions and roll back to a previous version.
- View policy code, assumptions, test evidence, and change history.
- View live evaluation stream and the normalized event that caused a decision.
- Run a policy against a selected historical event in dry-run mode.

The monitoring page must show event received time, normalized time, evaluation time, policy version, decision, reason, action state, and correlation ID. It should also show evaluation latency, dropped/unsupported event counts, and the latest connector watermark.

### 5.5 Actions

Actions are response definitions that policies may invoke. The first release supports:

- **Allow** — record the decision and continue.
- **Block** — call a configured vendor control, such as revoke a session, block a token, quarantine a repository, or deny an access request. The supported control must be explicit per vendor.
- **MFA** — request or enforce step-up authentication through a configured identity provider.
- **Escalate** — send a structured incident notification to configured email recipients, including justification, event evidence, policy name/version, severity, and action result.

Every action has mode and safety controls:

- Dry-run: record what would happen without changing an external system.
- Require approval: queue the action for an authorized reviewer.
- Automatic: execute immediately when policy and workspace permissions allow it.

Action configuration includes name, action type, target provider, credentials reference, retry policy, timeout, approval requirement, recipients, and template. Secrets are referenced, never embedded in policy code or email templates.

Action execution must be idempotent. A retry must not send duplicate escalations or apply the same block repeatedly when the provider supports idempotency keys.

## 6. Key user journeys

### Journey A: connect GitHub and verify activity

1. Administrator opens Vendors and selects GitHub.
2. Administrator enters organization details and token/OAuth configuration.
3. System tests credentials and reports API, scopes, webhook, and sample-event status.
4. If scopes are missing, system provides a remediation checklist and does not claim the connection is ready.
5. Administrator enables the connection.
6. System displays incoming events, connector lag, event type, actor, repository, and ingestion timestamp.

### Journey B: create a suspicious-hours policy

1. Security engineer opens Policy Agent and selects GitHub activity.
2. Engineer enters the natural-language scenario and selects the organization time zone.
3. Agent generates the policy, assumptions, required fields, and test scenarios.
4. Test runner executes every scenario in the isolated policy runtime.
5. The agent revises the policy until mandatory scenarios pass, or reports an unresolved ambiguity.
6. Engineer reviews and deploys the immutable version.

### Journey C: detect and respond

1. A vendor event is accepted, deduplicated, normalized, and placed on the evaluation stream.
2. Enabled policies subscribed to the event type evaluate it.
3. A policy decision and evidence record are persisted.
4. The configured action runs in dry-run, approval, or automatic mode.
5. The live monitoring page shows the event, policy decision, action status, and correlation ID.
6. An incident responder can inspect evidence, approve/reject a pending action, or disable the policy.

## 7. Permissions and governance

Recommended roles:

| Role | Vendor config | Create policy | Deploy | Enable/disable | Approve action | Audit |
|---|---:|---:|---:|---:|---:|---:|
| Viewer | No | No | No | No | No | Read |
| Analyst | Read | Yes | No | No | No | Read |
| Engineer | Yes | Yes | With approval | Yes | No | Read |
| Administrator | Yes | Yes | Yes | Yes | Yes | Read/write |
| Auditor | No | No | No | No | No | Read |

All material changes require an audit event. At minimum: credential created/rotated/deleted, connection enabled/disabled, prompt submitted, policy version generated, test run, deployment, rollback, policy enable/disable, action approval/rejection, and action execution.

## 8. Non-functional requirements

- Availability target: 99.9% for control-plane APIs in production.
- Event evaluation target: p95 under 10 seconds from accepted event to policy decision under normal load.
- UI freshness target: live monitoring updates within 5 seconds of a persisted decision.
- No event or secret loss during a worker restart; ingestion and evaluation use durable queues.
- Tenant/workspace data isolation at every API and database access path.
- Encryption in transit and at rest; secrets use self-hosted OpenBao or envelope encryption.
- Audit events are append-only and retained according to workspace policy.
- All policy versions are immutable after deployment.
- Accessibility target: WCAG 2.1 AA for core workflows.
- Initial supported browser versions: latest two major versions of Chrome, Edge, Firefox, and Safari.

## 9. Product acceptance criteria

- A user can configure, test, enable, disable, and troubleshoot a vendor connection.
- The system distinguishes authentication success from event availability and gives actionable permission/activity guidance.
- A natural-language prompt produces a reviewable policy and test suite.
- Mandatory test scenarios must pass before deployment is available.
- A deployed policy can be enabled/disabled and evaluated against live normalized events.
- Every trigger shows the source event, policy version, reasoning, action status, and correlation ID.
- Actions support dry-run and idempotent retry behavior.
- A user without permission cannot view secrets, deploy policies, or approve actions.
- A complete audit trail exists for the policy and action lifecycle.

## 10. Suggested release plan

### Release 1: trusted vertical slice

GitHub webhook/API connector, one workspace, Policy Agent, isolated test runner, deployed-policy monitoring, allow/escalate actions, and audit log.

### Release 2: operational coverage

GitLab, Jira, AWS CloudTrail, block/MFA action adapters, approvals, policy version rollback, historical replay, and richer diagnostics.

### Release 3: enterprise scale

Multi-workspace administration, SSO/SCIM, Azure/GCP/Okta connectors, connector marketplace, policy packs, high-availability deployment, and advanced analytics.
