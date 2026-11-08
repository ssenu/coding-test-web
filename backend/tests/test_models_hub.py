import asyncio

from sqlalchemy import inspect
from sqlmodel import Session

from app.models import Template
from app.ws.hub import Conn, Hub


def test_tables_created(app):
    names = set(inspect(app.state.engine).get_table_names())
    assert {
        "templates", "template_files", "runs", "run_files", "participants",
        "box_states", "edge_approvals", "submissions", "team_drafts", "team_versions",
    } <= names


def test_json_column_roundtrip(app):
    with Session(app.state.engine) as session:
        t = Template(name="t", graph={"boxes": [{"id": "x"}], "edges": []})
        session.add(t)
        session.commit()
        session.refresh(t)
        assert t.graph["boxes"][0]["id"] == "x"


class FakeSocket:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self.closed_with: int | None = None
        self.fail = fail

    async def send_json(self, data) -> None:
        if self.fail:
            raise RuntimeError("gone")
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


def test_hub_routes_messages_by_role():
    hub = Hub()
    admin, p1, p2 = FakeSocket(), FakeSocket(), FakeSocket()
    hub.connect(1, Conn(admin, "admin"))
    hub.connect(1, Conn(p1, "participant", participant_id=10))
    hub.connect(1, Conn(p2, "participant", participant_id=11))

    async def scenario():
        await hub.to_admins(1, "a", {})
        await hub.to_participants(1, "p", {}, exclude=10)
        await hub.to_all(1, "all", {"x": 1})

    asyncio.run(scenario())
    assert [m["event"] for m in admin.sent] == ["a", "all"]
    assert [m["event"] for m in p1.sent] == ["all"]
    assert [m["event"] for m in p2.sent] == ["p", "all"]
    assert hub.online(1) == {10, 11}


def test_hub_drops_broken_socket_and_kicks():
    hub = Hub()
    broken, old, new = FakeSocket(fail=True), FakeSocket(), FakeSocket()
    hub.connect(1, Conn(broken, "participant", participant_id=1))
    hub.connect(1, Conn(old, "participant", participant_id=2, token_hash="old"))
    hub.connect(1, Conn(new, "participant", participant_id=2, token_hash="new"))

    async def scenario():
        await hub.to_all(1, "x", {})
        await hub.kick(1, 2, keep_token_hash="new")

    asyncio.run(scenario())
    assert hub.online(1) == {2}
    assert old.closed_with == 4401
    assert new.closed_with is None
