"""Minimal Ollama Cloud client used to plan policy drafts.

The model may describe a policy, but it never supplies executable policy source. The
policy module continues to create and validate the restricted deterministic artifact.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyPlan:
    summary: str
    assumptions: list[str]


class OllamaPolicyPlanner:
    def __init__(self) -> None:
        self.api_key = os.getenv("OLLAMA_API_KEY", "").strip()
        self.base_url = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "20"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url)

    def plan(self, *, prompt: str, timezone: str, event_types: list[str]) -> PolicyPlan | None:
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
                        "You are a security policy planner. Return JSON only with keys "
                        "summary (a concise plain-text description) and assumptions (an array "
                        "of at most 4 concise plain-text strings). Do not return code, markdown, "
                        "credentials, or instructions to execute actions."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"risk_scenario": prompt, "timezone": timezone, "event_types": event_types}),
                },
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body: dict[str, Any] = json.loads(response.read().decode())
            content = body.get("message", {}).get("content", "")
            data = json.loads(content)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
            return None

        summary = data.get("summary")
        assumptions = data.get("assumptions")
        if not isinstance(summary, str) or not summary.strip() or not isinstance(assumptions, list):
            return None
        safe_assumptions = [item.strip() for item in assumptions if isinstance(item, str) and item.strip()][:4]
        return PolicyPlan(summary=summary.strip()[:1000], assumptions=safe_assumptions)
