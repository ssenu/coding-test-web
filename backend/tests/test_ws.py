import pytest
from starlette.websockets import WebSocketDisconnect

from app.auth import ADMIN_COOKIE
from tests.helpers import approve_all, open_run, started_parking_run, submit


def admin_ws(client, run_id: int):
    cookie = client.cookies.get(ADMIN_COOKIE)
    return client.websocket_connect(f"/ws/runs/{run_id}", headers={"cookie": f"{ADMIN_COOKIE}={cookie}"})


def participant_ws(client, run_id: int, token: str):
    return client.websocket_connect(f"/ws/runs/{run_id}?token={token}")


def receive_until(ws, event: str, limit: int = 20) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message["event"] == event:
            return message["data"]
    raise AssertionError(f"{event} 이벤트를 받지 못했습니다.")


def test_rejects_unauthenticated(admin_client):
    run = open_run(admin_client)
    with pytest.raises(WebSocketDisconnect) as bad_token:
        with participant_ws(admin_client, run["id"], "bad"):
            pass
    assert bad_token.value.code == 4401
    with pytest.raises(WebSocketDisconnect) as no_run:
        with admin_ws(admin_client, 9999):
            pass
    assert no_run.value.code == 4404
    admin_client.post("/api/admin/logout")
    with pytest.raises(WebSocketDisconnect) as no_cookie:
        with admin_client.websocket_connect(f"/ws/runs/{run['id']}"):
            pass
    assert no_cookie.value.code == 4401


def test_ping(admin_client):
    run = open_run(admin_client)
    with admin_ws(admin_client, run["id"]) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"event": "pong", "data": {}}


def test_admin_sees_presence_typing_and_submission(admin_client):
    ctx = started_parking_run(admin_client)
    run_id, token, pid = ctx["run"]["id"], ctx["tokens"]["a"], ctx["ids"]["a"]
    with admin_ws(admin_client, run_id) as admin:
        with participant_ws(admin_client, run_id, token) as p:
            online = receive_until(admin, "participant_updated")
            assert (online["id"], online["online"]) == (pid, True)
            assert admin_client.get(f"/api/runs/{run_id}/state").json()["participants"][0]["online"] is True

            p.send_json({"type": "typing"})
            typing = receive_until(admin, "participant_updated")
            assert typing["typing"] is True

            submit(admin_client, token, "a", "A")
            got = receive_until(admin, "submission_received")
            assert (got["box_id"], got["participant_id"]) == ("a", pid)
        offline = receive_until(admin, "participant_updated")
        assert offline["online"] is False


def test_box_state_changes_broadcast(admin_client):
    ctx = started_parking_run(admin_client)
    run_id = ctx["run"]["id"]
    with participant_ws(admin_client, run_id, ctx["tokens"]["b"]) as p:
        approve_all(admin_client, run_id)
        changes = [receive_until(p, "box_state_changed") for _ in range(5)]
        assert {(c["box_id"], c["state"]) for c in changes} == {
            ("team", "open"), ("a", "closed"), ("b", "closed"), ("c", "closed"), ("d", "closed"),
        }


def test_leader_draft_reaches_members(admin_client):
    ctx = started_parking_run(admin_client)
    run_id = ctx["run"]["id"]
    approve_all(admin_client, run_id)
    files = admin_client.get("/api/p/state", headers={"X-Participant-Token": ctx["tokens"]["a"]}).json()["team"]["team"]["files"]
    files["e_main.py"] = "live"
    with participant_ws(admin_client, run_id, ctx["tokens"]["b"]) as member:
        with participant_ws(admin_client, run_id, ctx["tokens"]["a"]) as leader:
            leader.send_json({"type": "team_draft", "box_id": "team", "files": files})
            draft = receive_until(member, "team_draft")
            assert draft["files"]["e_main.py"] == "live"
        with participant_ws(admin_client, run_id, ctx["tokens"]["c"]) as not_leader:
            not_leader.send_json({"type": "team_draft", "box_id": "team", "files": files})
            error = receive_until(not_leader, "error")
            assert error["detail"] == "팀장만 편집할 수 있습니다."
