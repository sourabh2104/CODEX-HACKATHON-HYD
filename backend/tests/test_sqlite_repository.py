from pathlib import Path

from app.models import Connection, ConnectionStatus
from app.repository import SQLiteRepository


def test_sqlite_repository_round_trips_non_secret_state(tmp_path: Path) -> None:
    path = tmp_path / "activity.db"
    first = SQLiteRepository(str(path))
    first.connections["conn_1"] = Connection(
        id="conn_1",
        workspace_id="default",
        vendor="github",
        name="GitHub",
        status=ConnectionStatus.CONNECTED,
        config={"organization": "example"},
        secret_ref="openbao://workspace/github/conn_1",
        secret_metadata={"configured": True, "last_four": "1234"},
    )
    first.set_secret("openbao://workspace/github/conn_1", "token-value")
    first.persist()

    second = SQLiteRepository(str(path))
    assert second.connections["conn_1"].config == {"organization": "example"}
    assert second.connections["conn_1"].secret_metadata["last_four"] == "1234"
    assert second.get_secret("openbao://workspace/github/conn_1") is None
