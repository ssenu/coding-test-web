from app.ratelimit import RateLimiter
from tests.helpers import assign, join, open_run, tok


def test_join_and_admin_sees_participant(admin_client):
    run = open_run(admin_client)
    joined = join(admin_client, run["entry_code"].lower(), " 김철수 ")
    assert joined["status"] == "joined"
    people = admin_client.get(f"/api/runs/{run['id']}/state").json()["participants"]
    assert [(p["name"], p["assigned_box_id"], p["is_leader"]) for p in people] == [("김철수", None, False)]


def test_join_wrong_code(client):
    r = client.post("/api/p/join", json={"entry_code": "ZZZZZZ", "name": "x"})
    assert r.status_code == 404


def test_join_finished_run_rejected(admin_client):
    run = open_run(admin_client)
    admin_client.post(f"/api/runs/{run['id']}/finish")
    r = admin_client.post("/api/p/join", json={"entry_code": run["entry_code"], "name": "x"})
    assert r.status_code == 404


def test_participant_token_required(client):
    assert client.get("/api/p/state").status_code == 401
    assert client.get("/api/p/state", headers=tok("bad")).status_code == 401


def test_assign_and_leader(admin_client):
    run = open_run(admin_client)
    p1 = join(admin_client, run["entry_code"], "가")["participant_id"]
    p2 = join(admin_client, run["entry_code"], "나")["participant_id"]
    assign(admin_client, run["id"], p1, "a", leader=True)
    assign(admin_client, run["id"], p2, "b", leader=True)
    people = {p["id"]: p for p in admin_client.get(f"/api/runs/{run['id']}/state").json()["participants"]}
    assert people[p1]["assigned_box_id"] == "a" and people[p1]["is_leader"] is False
    assert people[p2]["assigned_box_id"] == "b" and people[p2]["is_leader"] is True


def test_assign_rejects_taken_or_non_personal_box(admin_client):
    run = open_run(admin_client)
    p1 = join(admin_client, run["entry_code"], "가")["participant_id"]
    p2 = join(admin_client, run["entry_code"], "나")["participant_id"]
    assign(admin_client, run["id"], p1, "a")
    url = f"/api/runs/{run['id']}/participants/{p2}"
    assert admin_client.patch(url, json={"assigned_box_id": "a"}).status_code == 409
    assert admin_client.patch(url, json={"assigned_box_id": "team"}).status_code == 422
    # 배정 해제 후에는 다른 사람이 받을 수 있다
    assign(admin_client, run["id"], p1, None)
    assign(admin_client, run["id"], p2, "a")


def test_rejoin_needs_admin_approval(admin_client):
    run = open_run(admin_client)
    first = join(admin_client, run["entry_code"], "가")
    second = join(admin_client, run["entry_code"], "가")
    assert second["status"] == "pending"
    assert second["participant_id"] == first["participant_id"]
    assert admin_client.get("/api/p/state", headers=tok(second["token"])).status_code == 409
    people = admin_client.get(f"/api/runs/{run['id']}/state").json()["participants"]
    assert people[0]["rejoin_requested"] is True

    r = admin_client.post(f"/api/runs/{run['id']}/participants/{first['participant_id']}/approve-rejoin")
    assert r.status_code == 200
    assert admin_client.get("/api/p/state", headers=tok(second["token"])).status_code == 200
    assert admin_client.get("/api/p/state", headers=tok(first["token"])).status_code == 401
    again = admin_client.post(f"/api/runs/{run['id']}/participants/{first['participant_id']}/approve-rejoin")
    assert again.status_code == 409


def test_remove_participant(admin_client):
    run = open_run(admin_client)
    p = join(admin_client, run["entry_code"], "가")
    assert admin_client.delete(f"/api/runs/{run['id']}/participants/{p['participant_id']}").status_code == 204
    assert admin_client.get(f"/api/runs/{run['id']}/state").json()["participants"] == []


def test_join_rate_limited(client):
    for _ in range(10):
        assert client.post("/api/p/join", json={"entry_code": "ZZZZZZ", "name": "x"}).status_code == 404
    assert client.post("/api/p/join", json={"entry_code": "ZZZZZZ", "name": "x"}).status_code == 429


def test_rate_limiter_window():
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    assert limiter.allow("ip") and limiter.allow("ip")
    assert not limiter.allow("ip")
    assert limiter.allow("other")
    now[0] = 60.0
    assert limiter.allow("ip")
