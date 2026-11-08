from tests.helpers import create_template, open_run


def test_cannot_open_run_from_invalid_template(admin_client):
    t = admin_client.post("/api/templates", json={"name": "빈"}).json()
    r = admin_client.post(f"/api/templates/{t['id']}/runs", json={"name": "1기"})
    assert r.status_code == 409


def test_open_run_snapshot_and_lobby(admin_client):
    run = open_run(admin_client)
    assert run["status"] == "lobby"
    assert len(run["entry_code"]) == 6
    state = admin_client.get(f"/api/runs/{run['id']}/state").json()
    assert set(state["boxes"]) == {"story", "a", "b", "c", "d", "team", "result"}
    assert all(b["state"] == "locked" for b in state["boxes"].values())
    assert state["participants"] == []
    assert [r["id"] for r in admin_client.get("/api/runs").json()] == [run["id"]]


def test_template_edit_does_not_change_run(admin_client):
    t = create_template(admin_client)
    run = open_run(admin_client, t["id"])
    admin_client.put(f"/api/templates/{t['id']}", json={"name": "바뀜", "graph": {"boxes": [], "edges": []}})
    state = admin_client.get(f"/api/runs/{run['id']}/state").json()
    assert len(state["graph"]["boxes"]) == 7


def test_start_opens_personal_boxes(admin_client):
    run = open_run(admin_client)
    r = admin_client.post(f"/api/runs/{run['id']}/start")
    assert r.status_code == 200
    boxes = r.json()["boxes"]
    assert boxes["story"]["state"] == "closed"
    assert [boxes[x]["state"] for x in "abcd"] == ["open"] * 4
    assert boxes["team"]["state"] == "locked"
    assert admin_client.post(f"/api/runs/{run['id']}/start").status_code == 409


def test_template_with_run_cannot_be_deleted(admin_client):
    t = create_template(admin_client)
    open_run(admin_client, t["id"])
    assert admin_client.delete(f"/api/templates/{t['id']}").status_code == 409


def test_attachments_copied_into_run(admin_client):
    t = create_template(admin_client)
    admin_client.post(f"/api/templates/{t['id']}/files", data={"box_id": "story"}, files={"file": ("안내.txt", b"hi")})
    run = open_run(admin_client, t["id"])
    files = admin_client.get(f"/api/runs/{run['id']}/state").json()["files"]
    assert [f["filename"] for f in files["story"]] == ["안내.txt"]
    got = admin_client.get(f"/api/runs/{run['id']}/files/{files['story'][0]['id']}")
    assert got.content == b"hi"


def test_finish_run(admin_client):
    run = open_run(admin_client)
    assert admin_client.post(f"/api/runs/{run['id']}/finish").json()["run"]["status"] == "finished"
    assert admin_client.post(f"/api/runs/{run['id']}/finish").status_code == 409
