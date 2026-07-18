import json

from app.connectors import GitHubConnector
from app.models import Connection, ConnectionStatus


class FakeResponse:
    def __init__(self, payload):
        self.status = 200
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_github_connection_uses_api_and_normalizes_audit_events(monkeypatch):
    connector = GitHubConnector()
    connection = Connection(id="conn-test", workspace_id="workspace", vendor="github", name="Acme", status=ConnectionStatus.DRAFT, config={"organization": "acme", "api_url": "https://api.github.test"})
    connector.remember_token(connection.id, "token-from-user")

    def fake_urlopen(request, timeout):
        assert request.headers["Authorization"] == "Bearer token-from-user"
        if request.full_url.endswith("/user"):
            return FakeResponse({"login": "tester"})
        if "/audit-log" in request.full_url:
            return FakeResponse([{"id": "audit-1", "action": "repo.fork", "actor": "alice", "repo_name": "acme/payments", "@timestamp": 1784330400000}])
        return FakeResponse({"login": "acme"})

    monkeypatch.setattr("app.connectors.urllib.request.urlopen", fake_urlopen)
    result = connector.test_connection(connection)
    assert result.status == "passed"
    events = connector.fetch_events(connection)
    assert len(events) == 1
    assert events[0].event_type == "repository.fork"
    assert events[0].actor.id == "alice"
