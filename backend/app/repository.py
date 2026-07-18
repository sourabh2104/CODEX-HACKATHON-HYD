from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from typing import Any, Protocol, TypeVar

from .models import (
    ActionDefinition,
    ActionExecution,
    Approval,
    AuditEvent,
    Connection,
    Evaluation,
    NormalizedEvent,
    Policy,
    PolicyDraft,
    PolicyVersion,
)

T = TypeVar("T")


class Repository(Protocol):
    connections: dict[str, Connection]
    drafts: dict[str, PolicyDraft]
    policies: dict[str, Policy]
    versions: dict[str, PolicyVersion]
    events: dict[str, NormalizedEvent]
    evaluations: dict[str, Evaluation]
    actions: dict[str, ActionDefinition]
    action_executions: dict[str, ActionExecution]
    approvals: dict[str, Approval]
    audits: list[AuditEvent]


class InMemoryRepository:
    """Default store. The API depends on this narrow shape, not on its storage engine."""

    def __init__(self) -> None:
        self.connections: dict[str, Connection] = {}
        self.drafts: dict[str, PolicyDraft] = {}
        self.policies: dict[str, Policy] = {}
        self.versions: dict[str, PolicyVersion] = {}
        self.events: dict[str, NormalizedEvent] = {}
        self.evaluations: dict[str, Evaluation] = {}
        self.actions: dict[str, ActionDefinition] = {}
        self.action_executions: dict[str, ActionExecution] = {}
        self.approvals: dict[str, Approval] = {}
        self.audits: list[AuditEvent] = []
        self.secret_values: dict[str, str] = {}
        self._dedupe: set[tuple[str, str]] = set()
        self._idempotency: dict[str, str] = {}

    def is_duplicate(self, workspace_id: str, key: str) -> bool:
        marker = (workspace_id, key)
        if marker in self._dedupe:
            return True
        self._dedupe.add(marker)
        return False

    def find_connection(self, workspace_id: str, connection_id: str) -> Connection | None:
        item = self.connections.get(connection_id)
        return item if item and item.workspace_id == workspace_id else None

    def find_event(self, workspace_id: str, event_id: str) -> NormalizedEvent | None:
        item = self.events.get(event_id)
        return item if item and item.workspace_id == workspace_id else None

    def action_by_idempotency(self, key: str) -> ActionExecution | None:
        value = self._idempotency.get(key)
        return self.action_executions.get(value) if value else None

    def record_action(self, execution: ActionExecution) -> None:
        self.action_executions[execution.id] = execution
        self._idempotency[execution.idempotency_key] = execution.id

    def list_workspace(self, collection: dict[str, T], workspace_id: str) -> list[T]:
        return [item for item in collection.values() if getattr(item, "workspace_id", None) == workspace_id]

    def set_secret(self, reference: str | None, value: str | None) -> None:
        if reference and value:
            self.secret_values[reference] = value

    def get_secret(self, reference: str | None) -> str | None:
        return self.secret_values.get(reference or "")

    def persist(self) -> None:
        return None


class SQLiteRepository(InMemoryRepository):
    """Small local persistence adapter for the demo and offline development.

    It persists application state but deliberately never persists raw credential values.
    Production deployments can replace this adapter with PostgreSQL without changing the API layer.
    """

    _collections = {
        "connections": (Connection, "id"),
        "drafts": (PolicyDraft, "id"),
        "policies": (Policy, "id"),
        "versions": (PolicyVersion, "id"),
        "events": (NormalizedEvent, "event_id"),
        "evaluations": (Evaluation, "id"),
        "actions": (ActionDefinition, "id"),
        "action_executions": (ActionExecution, "id"),
        "approvals": (Approval, "id"),
    }

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS state (collection TEXT NOT NULL, item_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (collection, item_id))")
            db.commit()
        self._load()

    def _load(self) -> None:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT collection, item_id, payload FROM state").fetchall()
        for collection, item_id, payload in rows:
            model_type, key = self._collections.get(collection, (None, None))
            if not model_type:
                continue
            item = model_type.model_validate(json.loads(payload))
            getattr(self, collection)[getattr(item, key)] = item

    def persist(self) -> None:
        with sqlite3.connect(self.path) as db:
            for collection, (model_type, key) in self._collections.items():
                values = getattr(self, collection)
                db.execute("DELETE FROM state WHERE collection = ?", (collection,))
                db.executemany(
                    "INSERT INTO state (collection, item_id, payload) VALUES (?, ?, ?)",
                    [(collection, str(getattr(item, key)), json.dumps(item.model_dump(mode="json"))) for item in values.values()],
                )
            db.commit()
