"""Ollama Cloud client for policy planning.

The model returns a declarative policy plan only. It never returns or executes Python;
the policy module validates the plan and builds the restricted evaluator artifact.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class PolicyPlanningError(RuntimeError):
    """The configured LLM could not produce a valid policy plan."""


@dataclass(frozen=True)
class PolicyPlan:
    policy_name: str
    summary: str
    assumptions: list[str]
    event_types: list[str]
    quiet_start: int
    quiet_end: int


class OllamaPolicyPlanner:
    def __init__(self) -> None:
        self.api_key = os.getenv("OLLAMA_API_KEY", "").strip()
        self.base_url = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "minimax-m2.5")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url)

    def plan(self, *, prompt: str, timezone: str, event_types: list[str], policy_name: str) -> PolicyPlan | None:
        """Return a model plan, or None only when no LLM has been configured."""
        if not self.enabled:
            return None
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a security policy planner for GitHub normalized events. Return JSON only, "
                        "with policy_name (string), summary (string), assumptions (array of at most 4 strings), "
                        "event_types (array using only repository.commit, repository.clone, repository.fork), "
                        "quiet_start (integer hour 0-23), and quiet_end (integer hour 0-23). "
                        "Choose a non-empty, non-wrapping interval; use quiet_end 24 for midnight. "
                        "Do not return code, Markdown, credentials, or action instructions."
                    ),
                },
                {"role": "user", "content": json.dumps({"risk_scenario": prompt, "timezone": timezone, "requested_event_types": event_types, "requested_policy_name": policy_name})},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": "activity-policy-control-plane/0.1"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body: dict[str, Any] = json.loads(response.read().decode())
            content = body.get("message", {}).get("content", "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else ""
                if content.endswith("```"):
                    content = content[:-3].strip()
            data = json.loads(content)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            raise PolicyPlanningError("The configured Ollama model could not generate a policy plan.") from exc

        try:
            name = self._text(data["policy_name"], 200)
            summary = self._text(data["summary"], 1000)
            assumptions = [self._text(item, 500) for item in data["assumptions"][:4]]
            allowed_events = {"repository.commit", "repository.clone", "repository.fork"}
            selected_events = [item for item in data["event_types"] if isinstance(item, str) and item in allowed_events]
            start, end = int(data["quiet_start"]), int(data["quiet_end"])
            if not name or not summary or not assumptions or not selected_events or not 0 <= start <= 23 or not 1 <= end <= 24 or start >= end:
                raise ValueError("invalid policy plan")
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyPlanningError("The configured Ollama model returned an invalid policy plan.") from exc
        return PolicyPlan(name, summary, assumptions, selected_events, start, end)

    @staticmethod
    def _text(value: Any, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("expected non-empty text")
        return value.strip()[:maximum]
