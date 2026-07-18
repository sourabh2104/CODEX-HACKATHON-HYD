# Project documentation

These documents define the Activity Policy Control Plane from product intent through implementation:

- [Product Requirements](./PRODUCT_REQUIREMENTS.md) — goals, personas, sidebar workflows, vendor behavior, policy lifecycle, actions, permissions, acceptance criteria, and release plan.
- [Technical Specification](./TECHNICAL_SPECIFICATION.md) — domain model, event contract, connector and policy interfaces, API surface, processing semantics, security, reliability, and testing.
- [Implementation Architecture](./IMPLEMENTATION_ARCHITECTURE.md) — component boundaries, data flows, repository layout, deployment topology, trust boundaries, failure handling, and phased build plan.
- [Architectural Flow Diagram](./ARCHITECTURAL_FLOW.md) — end-to-end Mermaid diagrams for onboarding, ingestion, policy generation, deployment, evaluation, response actions, failure handling, audit, and observability.

The technical baseline is self-hosted and open-source/free: React/Vite, FastAPI, PostgreSQL, NATS JetStream, Valkey, Keycloak, OpenBao, MinIO, Ollama, Prometheus, Grafana, Loki, Docker, and Kubernetes. Paid cloud infrastructure and vendor API usage are optional operational costs, not required software dependencies.

The recommended first delivery is the GitHub-to-policy-to-monitoring vertical slice with allow and escalation actions. Additional vendors and response adapters should be added through the connector/action contracts documented in the technical specification.

## Current implementation status

The checked-in vertical slice currently implements FastAPI + React/Vite, a SQLite repository adapter, real GitHub PAT/API connection diagnostics, GitHub audit-event normalization, webhook ingestion, deterministic policy artifact generation and scenario testing, policy deployment/toggling, action definitions, and audit/evaluation records. PostgreSQL, NATS, Valkey, Keycloak, OpenBao, MinIO, and Ollama remain documented self-hosted integration targets; they are compose scaffolding rather than claims of already-wired runtime dependencies. The local demo dataset is opt-in/explicitly labeled, and live API failures do not fall back to it.
