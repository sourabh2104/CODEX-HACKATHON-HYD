from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from .models import (
    Check,
    CheckStatus,
    Connection,
    ConnectionTest,
    EventActor,
    EventResource,
    EventSource,
    NormalizedEvent,
    Remediation,
    VendorDefinition,
    utcnow,
)


class Connector(Protocol):
    vendor: str

    def test_connection(self, connection: Connection) -> ConnectionTest: ...
    def normalize(self, payload: dict[str, Any], connection: Connection, received_at: datetime) -> NormalizedEvent: ...
    def verify_webhook(self, headers: dict[str, str], body: bytes, connection: Connection) -> bool: ...
    def fetch_events(self, connection: Connection) -> list[NormalizedEvent]: ...


VENDORS = [
    VendorDefinition(
        key="github", display_name="GitHub", category="version_control",
        auth_methods=["personal_access_token", "oauth_app"], ingestion_modes=["webhook", "poll"],
        event_types=["repository.commit", "repository.clone", "repository.fork", "identity.login"],
        required_scopes=["audit:read"], capabilities=["audit_log", "webhooks", "sample_events"],
    ),
    VendorDefinition(
        key="gitlab", display_name="GitLab", category="version_control",
        auth_methods=["personal_access_token", "oauth_app"], ingestion_modes=["webhook", "poll"],
        event_types=["repository.push", "repository.fork", "identity.login"],
        required_scopes=["read_api"], capabilities=["audit_log", "webhooks"],
    ),
    VendorDefinition(
        key="generic-webhook", display_name="Generic Git Webhook", category="version_control",
        auth_methods=["webhook_secret"], ingestion_modes=["webhook"],
        event_types=["repository.commit", "repository.clone", "repository.fork"],
        required_scopes=[], capabilities=["webhooks"],
    ),
]


class GitHubConnector:
    vendor = "github"

    def __init__(self) -> None:
        self._webhook_secrets: dict[str, str] = {}
        self._tokens: dict[str, str] = {}
        self._last_events: dict[str, list[NormalizedEvent]] = {}

    def remember_token(self, connection_id: str, token: str) -> None:
        self._tokens[connection_id] = token

    def remember_webhook_secret(self, connection_id: str, secret: str) -> None:
        self._webhook_secrets[connection_id] = secret

    def test_connection(self, connection: Connection) -> ConnectionTest:
        token = self._tokens.get(connection.id)
        if not token:
            return ConnectionTest(status="failed", checks=[
                Check(name="credentials", status=CheckStatus.FAILED, code="MISSING_CREDENTIALS", message="A GitHub personal access token is required."),
                Check(name="api_reachability", status=CheckStatus.SKIPPED), Check(name="required_scopes", status=CheckStatus.SKIPPED),
                Check(name="event_subscription", status=CheckStatus.SKIPPED), Check(name="sample_event", status=CheckStatus.NOT_AVAILABLE),
            ], remediation=Remediation(summary="Add a GitHub personal access token with organization audit-log access.", steps=["Create or select a GitHub PAT.", "Grant organization Administration: read access, or the equivalent audit-log permission for your GitHub plan.", "Save the credential and test again."], test_actions=["After connecting, create a test branch or fork in the organization."]))
        org = str(connection.config.get("organization") or connection.config.get("organization_name") or "").strip()
        if not org:
            return ConnectionTest(status="failed", checks=[Check(name="credentials", status=CheckStatus.PASSED), Check(name="api_reachability", status=CheckStatus.SKIPPED), Check(name="required_scopes", status=CheckStatus.SKIPPED), Check(name="event_subscription", status=CheckStatus.SKIPPED), Check(name="sample_event", status=CheckStatus.NOT_AVAILABLE)], remediation=Remediation(summary="Enter the GitHub organization name before testing.", steps=["Enter the organization login exactly as shown in GitHub.", "Test the connection again."], test_actions=[]))
        checks = [Check(name="credentials", status=CheckStatus.PASSED), Check(name="api_reachability", status=CheckStatus.PASSED), Check(name="required_scopes", status=CheckStatus.PASSED), Check(name="event_subscription", status=CheckStatus.PASSED), Check(name="sample_event", status=CheckStatus.NOT_AVAILABLE, code="NO_ACTIVITY")]
        organization_url = str(connection.config.get("organization_url") or "").strip()
        parsed_organization_url = urllib.parse.urlparse(organization_url)
        organization_path = parsed_organization_url.path.strip("/").split("/")[-1] if parsed_organization_url.path.strip("/") else ""
        if parsed_organization_url.hostname in {"github.com", "www.github.com"} and organization_path and organization_path.lower() != org.lower():
            checks[2] = Check(name="required_scopes", status=CheckStatus.FAILED, code="ORG_URL_MISMATCH", message=f"Organization name '{org}' does not match the organization URL path '{organization_path}'.")
            return ConnectionTest(status="failed", checks=checks, remediation=Remediation(summary="The organization name and organization URL do not match.", steps=[f"Use '{organization_path}' as the organization login, or change the organization URL to the page for '{org}'.", "Use an organization URL, not a personal profile URL.", "Save the credential and test again."], test_actions=[]))
        try:
            user_status, _ = self._request(connection, "/user")
            if user_status == 401:
                checks[0] = Check(name="credentials", status=CheckStatus.FAILED, code="INVALID_CREDENTIALS", message="GitHub rejected the personal access token.")
                checks[1] = Check(name="api_reachability", status=CheckStatus.SKIPPED)
                checks[2] = Check(name="required_scopes", status=CheckStatus.SKIPPED)
                return ConnectionTest(status="failed", checks=checks, remediation=Remediation(summary="The GitHub token was rejected.", steps=["Verify the token is active and copied correctly.", "Rotate the token if it has expired.", "Save the new credential and test again."], test_actions=[]))
            if user_status == 404:
                checks[1] = Check(name="api_reachability", status=CheckStatus.FAILED, code="API_URL_NOT_FOUND", message="The configured API URL returned 404 for /user. Use https://api.github.com for GitHub.com, or the /api/v3 endpoint for GitHub Enterprise Server.")
                checks[2] = Check(name="required_scopes", status=CheckStatus.SKIPPED)
                return ConnectionTest(status="failed", checks=checks, remediation=Remediation(summary="The GitHub API URL is not the GitHub API endpoint.", steps=["Set GitHub API URL to https://api.github.com for GitHub.com.", "For GitHub Enterprise Server, use https://<hostname>/api/v3.", "Keep the organization URL separate from the API URL."], test_actions=[]))
            if user_status >= 400:
                raise RuntimeError(f"GitHub API returned HTTP {user_status} while validating credentials")
            org_status, _ = self._request(connection, f"/orgs/{urllib.parse.quote(org)}")
            if org_status in {401, 403, 404}:
                checks[2] = Check(name="required_scopes", status=CheckStatus.FAILED, code="MISSING_ORG_ACCESS", message="The token cannot read this organization.")
                if org_status == 404:
                    checks[2] = Check(name="required_scopes", status=CheckStatus.FAILED, code="ORG_NOT_FOUND", message=f"GitHub could not find organization '{org}'. Enter the organization login exactly as shown in the organization URL.")
                checks[3] = Check(name="event_subscription", status=CheckStatus.SKIPPED)
                summary = "The organization login was not found." if org_status == 404 else "Grant the token organization read access and audit-log access."
                steps = ["Confirm the organization login matches the final path segment of the organization URL.", "Do not use a personal GitHub username unless it is the organization login.", "Save the credential and test again."] if org_status == 404 else ["Grant Administration: read access to the fine-grained token, or the required organization audit permission.", "Confirm the organization login is correct.", "Save the credential and test again."]
                return ConnectionTest(status="degraded", checks=checks, remediation=Remediation(summary=summary, steps=steps, test_actions=["Create a test branch or fork after access is granted."]))
            audit_status, audit_payload = self._request(connection, f"/orgs/{urllib.parse.quote(org)}/audit-log?per_page=20")
            if audit_status in {401, 403, 404}:
                checks[2] = Check(name="required_scopes", status=CheckStatus.FAILED, code="MISSING_AUDIT_ACCESS", message="The token cannot read the organization audit log.")
                checks[3] = Check(name="event_subscription", status=CheckStatus.SKIPPED)
                return ConnectionTest(status="degraded", checks=checks, remediation=Remediation(summary="The token is valid but lacks organization audit-log access.", steps=["Grant the organization audit-log permission to the token.", "Save the updated credential and test again."], test_actions=["Create a test branch, fork, or clone event after the permission is granted."]))
            if audit_status >= 400:
                raise RuntimeError(f"GitHub audit-log request returned HTTP {audit_status}")
            payloads = audit_payload if isinstance(audit_payload, list) else []
            events = [self.normalize(payload, connection, utcnow()) for payload in payloads if isinstance(payload, dict)]
            self._last_events[connection.id] = events
            if events:
                checks[4] = Check(name="sample_event", status=CheckStatus.PASSED, message=f"Retrieved {len(events)} audit events.")
                return ConnectionTest(status="passed", checks=checks, remediation=None)
            return ConnectionTest(status="degraded", checks=checks, remediation=Remediation(summary="The GitHub API is reachable, but no audit events were returned.", steps=["Confirm the token can read organization audit logs.", "Keep the connection enabled and wait for a new activity event."], test_actions=["Create a test branch, fork a non-production repository, or clone a repository in the organization."]))
        except urllib.error.URLError as exc:
            return ConnectionTest(status="failed", checks=[checks[0], Check(name="api_reachability", status=CheckStatus.FAILED, code="API_UNREACHABLE", message=str(exc.reason)), Check(name="required_scopes", status=CheckStatus.SKIPPED), Check(name="event_subscription", status=CheckStatus.SKIPPED), Check(name="sample_event", status=CheckStatus.NOT_AVAILABLE)], remediation=Remediation(summary="The GitHub API could not be reached.", steps=["Check the API URL and network access from the backend.", "Try the connection test again."], test_actions=[]))
        except Exception as exc:
            return ConnectionTest(status="failed", checks=[checks[0], Check(name="api_reachability", status=CheckStatus.FAILED, code="GITHUB_API_ERROR", message=str(exc)), Check(name="required_scopes", status=CheckStatus.SKIPPED), Check(name="event_subscription", status=CheckStatus.SKIPPED), Check(name="sample_event", status=CheckStatus.NOT_AVAILABLE)], remediation=Remediation(summary="GitHub returned an unexpected response.", steps=["Inspect the API URL and organization name.", "Try the connection test again."], test_actions=[]))

    def _request(self, connection: Connection, path: str) -> tuple[int, Any]:
        configured_url = str(connection.config.get("api_url") or "https://api.github.com").rstrip("/")
        parsed_url = urllib.parse.urlparse(configured_url)
        if parsed_url.hostname in {"github.com", "www.github.com"}:
            # A common setup mistake is entering the organization web URL in the API URL field.
            # Correct only GitHub.com; Enterprise Server requires its explicit /api/v3 endpoint.
            api_url = "https://api.github.com"
            connection.config["api_url"] = api_url
        else:
            api_url = configured_url
        request = urllib.request.Request(f"{api_url}{path}", headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self._tokens[connection.id]}", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "activity-policy-control-plane"})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                return response.status, json.loads(response.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8") or "null")
            except Exception:
                body = None
            return exc.code, body

    def fetch_events(self, connection: Connection) -> list[NormalizedEvent]:
        return self._last_events.get(connection.id, [])

    def verify_webhook(self, headers: dict[str, str], body: bytes, connection: Connection) -> bool:
        expected = self._webhook_secrets.get(connection.id)
        signature = headers.get("x-hub-signature-256") or headers.get("x-webhook-signature")
        if not expected:
            return True
        if not signature:
            return False
        digest = "sha256=" + hmac.new(str(expected).encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, signature)

    def normalize(self, payload: dict[str, Any], connection: Connection, received_at: datetime) -> NormalizedEvent:
        event_type = payload.get("event_type") or payload.get("type") or self._event_type(payload)
        source_id = str(payload.get("id") or payload.get("delivery_id") or uuid4().hex)
        actor_data = payload.get("actor") or payload.get("sender") or {"id": payload.get("actor_name") or payload.get("user")}
        if not isinstance(actor_data, dict):
            actor_data = {"id": str(actor_data)}
        repo = payload.get("repository") or payload.get("resource") or payload.get("repo") or {"name": payload.get("repo_name")}
        if isinstance(repo, str):
            repo_name = repo.rsplit("/", 1)[-1]
            repo = {"name": repo_name, "full_name": repo}
        organization = payload.get("organization") or payload.get("org")
        occurred = payload.get("occurred_at") or payload.get("created_at") or payload.get("@timestamp") or received_at
        if isinstance(occurred, (int, float)):
            occurred = datetime.fromtimestamp(occurred / 1000 if occurred > 10_000_000_000 else occurred, tz=timezone.utc)
        if isinstance(occurred, str):
            occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        return NormalizedEvent(
            event_id=f"evt_{source_id}", workspace_id=connection.workspace_id, connection_id=connection.id,
            vendor=connection.vendor, event_type=event_type, occurred_at=occurred, received_at=received_at,
            actor=EventActor(id=str(actor_data.get("id") or actor_data.get("login") or "") or None, name=actor_data.get("name") or actor_data.get("login"), type=actor_data.get("type", "human"), service_account=bool(actor_data.get("service_account", False))),
            resource=EventResource(type="repository", id=str(repo.get("id") or "") or None, name=repo.get("name"), organization=repo.get("organization") or organization or repo.get("full_name", "").split("/")[0] or connection.config.get("organization")),
            source=EventSource(event_id=source_id, url=payload.get("url"), ip=payload.get("ip"), user_agent=payload.get("user_agent")),
            attributes=dict(payload.get("attributes") or {key: payload[key] for key in ("action", "visibility", "ref") if key in payload}),
            raw_payload_ref=f"memory://raw/{source_id}", dedupe_key=f"{connection.vendor}:{source_id}",
            normalization_status="complete" if event_type else "partial",
        )

    @staticmethod
    def _event_type(payload: dict[str, Any]) -> str:
        action = str(payload.get("action") or payload.get("operation") or payload.get("user_agent") or "activity").lower()
        if "fork" in action:
            return "repository.fork"
        if "clone" in action or "git." in action or "download_zip" in action or action == "repo.access":
            return "repository.clone"
        if "commit" in action or "push" in action:
            return "repository.commit"
        if "login" in action or "authentication" in action:
            return "identity.login"
        return f"github.{action.replace(' ', '_')}"


CONNECTORS: dict[str, Connector] = {"github": GitHubConnector(), "gitlab": GitHubConnector(), "generic-webhook": GitHubConnector()}
