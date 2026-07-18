"""Replaceable boundaries for production adapters.

The default API uses the in-memory repository and no external services. PostgreSQL,
NATS/JetStream, and OpenBao adapters can implement these protocols without changing
the domain or HTTP contract.
"""

from __future__ import annotations

from typing import Any, Protocol


class SecretStore(Protocol):
    def put_reference(self, workspace_id: str, purpose: str, value: str) -> str: ...
    def resolve(self, reference: str) -> str: ...
    def revoke(self, reference: str) -> None: ...


class EventBus(Protocol):
    def publish(self, subject: str, payload: dict[str, Any], *, correlation_id: str | None = None) -> str: ...
    def subscribe(self, subject: str, handler: Any) -> None: ...


class PolicyRepository(Protocol):
    def get(self, workspace_id: str, resource_id: str) -> Any: ...
    def save(self, resource: Any) -> Any: ...
    def list(self, workspace_id: str) -> list[Any]: ...

