from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class APIModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class ConnectionStatus(str, Enum):
    DRAFT = "draft"
    TESTING = "testing"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    FAILED = "failed"
    DISABLED = "disabled"


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_AVAILABLE = "not_available"


class PolicyStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    DEPLOYING = "deploying"
    ENABLED = "enabled"
    DISABLED = "disabled"
    RETIRED = "retired"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    MFA = "mfa"
    ESCALATE = "escalate"


class ActionMode(str, Enum):
    DRY_RUN = "dry_run"
    APPROVAL = "approval"
    AUTOMATIC = "automatic"


class ActionStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventActor(APIModel):
    id: str | None = None
    type: str = "human"
    name: str | None = None
    service_account: bool = False


class EventResource(APIModel):
    type: str | None = None
    id: str | None = None
    name: str | None = None
    organization: str | None = None


class EventSource(APIModel):
    event_id: str | None = None
    url: str | None = None
    ip: str | None = None
    user_agent: str | None = None


class NormalizedEvent(APIModel):
    schema_version: str = "1.0"
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    workspace_id: str = "default"
    connection_id: str
    vendor: str
    event_type: str
    occurred_at: datetime
    received_at: datetime = Field(default_factory=utcnow)
    actor: EventActor = Field(default_factory=EventActor)
    resource: EventResource = Field(default_factory=EventResource)
    source: EventSource = Field(default_factory=EventSource)
    attributes: dict[str, Any] = Field(default_factory=dict)
    raw_payload_ref: str | None = None
    dedupe_key: str
    normalization_status: Literal["unsupported", "partial", "complete"] = "complete"

    @field_validator("occurred_at", "received_at", mode="before")
    @classmethod
    def ensure_datetime(cls, value: Any) -> datetime:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


class PolicyDecision(APIModel):
    matched: bool
    severity: Severity
    reason_code: str
    explanation: str
    evidence: dict[str, str] = Field(default_factory=dict)
    action_ref: str | None = None


class Check(APIModel):
    name: str
    status: CheckStatus
    code: str | None = None
    message: str | None = None


class Remediation(APIModel):
    summary: str
    steps: list[str] = Field(default_factory=list)
    test_actions: list[str] = Field(default_factory=list)


class ConnectionTest(APIModel):
    status: Literal["passed", "degraded", "failed"]
    checks: list[Check]
    remediation: Remediation | None = None
    tested_at: datetime = Field(default_factory=utcnow)


class VendorDefinition(APIModel):
    key: str
    display_name: str
    category: str
    auth_methods: list[str]
    ingestion_modes: list[str]
    event_types: list[str]
    required_scopes: list[str]
    capabilities: list[str]


class ConnectionCreate(APIModel):
    vendor: str
    name: str = Field(min_length=1, max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)
    secret_ref: str | None = None
    requested_event_types: list[str] = Field(default_factory=list)


class Connection(APIModel):
    id: str
    workspace_id: str
    vendor: str
    name: str
    status: ConnectionStatus
    enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    secret_ref: str | None = None
    secret_metadata: dict[str, Any] = Field(default_factory=dict)
    last_test: ConnectionTest | None = None
    last_ingestion_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PolicyDraftCreate(APIModel):
    prompt: str = Field(min_length=10, max_length=5000)
    name: str | None = None
    vendor: str = "github"
    event_types: list[str] = Field(default_factory=list)
    timezone: str = "UTC"
    business_hours: dict[str, Any] = Field(default_factory=dict)
    exclusions: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = Severity.HIGH
    action_ref: str | None = None
    tags: list[str] = Field(default_factory=list)


class TestCase(APIModel):
    name: str
    input_event: dict[str, Any]
    expected_matched: bool
    mandatory: bool = True
    scenario_type: str = "custom"


class TestResult(APIModel):
    case_name: str
    expected_matched: bool
    actual_matched: bool | None = None
    passed: bool
    reason_code: str | None = None
    explanation: str | None = None
    trace: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class TestRun(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: Literal["passed", "failed"]
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime = Field(default_factory=utcnow)
    results: list[TestResult]
    summary: dict[str, int]


class PolicyArtifact(APIModel):
    policy_name: str
    summary: str
    intent: dict[str, Any]
    required_event_types: list[str]
    required_fields: list[str]
    assumptions: list[str]
    severity: Severity
    action_ref: str | None = None
    python_source: str
    source_sha256: str
    generator: str = "deterministic-suspicious-hours-v1"
    sdk_version: str = "1.0"
    test_cases: list[TestCase]


class PolicyDraft(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    name: str
    prompt: str
    vendor: str
    event_types: list[str]
    timezone: str
    business_hours: dict[str, Any]
    exclusions: dict[str, Any]
    severity: Severity
    action_ref: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: PolicyStatus = PolicyStatus.DRAFT
    artifact: PolicyArtifact | None = None
    latest_test_run: TestRun | None = None
    policy_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PolicyVersion(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    policy_id: str
    version: int
    workspace_id: str
    artifact: PolicyArtifact
    status: PolicyStatus = PolicyStatus.ENABLED
    deployed_at: datetime = Field(default_factory=utcnow)
    disabled_at: datetime | None = None


class Policy(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    name: str
    vendor: str
    severity: Severity
    tags: list[str] = Field(default_factory=list)
    status: PolicyStatus = PolicyStatus.ENABLED
    current_version_id: str
    version: int
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ActionCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    action_type: ActionType
    mode: ActionMode = ActionMode.DRY_RUN
    provider: str | None = None
    secret_ref: str | None = None
    recipients: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=10, ge=1, le=300)


class ActionDefinition(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    name: str
    action_type: ActionType
    mode: ActionMode
    provider: str | None = None
    secret_ref: str | None = None
    recipients: list[str] = Field(default_factory=list)
    timeout_seconds: int = 10
    enabled: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class Evaluation(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    event_id: str
    policy_id: str
    policy_version_id: str
    vendor: str
    decision: PolicyDecision
    evaluated_at: datetime = Field(default_factory=utcnow)
    latency_ms: float = 0.0
    correlation_id: str = Field(default_factory=lambda: f"cor_{uuid4().hex}")
    action_execution_id: str | None = None


class ActionExecution(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    evaluation_id: str
    action_ref: str
    action_type: ActionType
    mode: ActionMode
    status: ActionStatus
    idempotency_key: str
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class Approval(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    action_execution_id: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    justification: str | None = None
    decided_at: datetime | None = None


class AuditEvent(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    action: str
    target_type: str
    target_id: str
    actor: str = "system"
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    correlation_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)

