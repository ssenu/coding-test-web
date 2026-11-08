from tests.helpers import assign, create_template, join, open_run, started_parking_run, tok


def boxes_of(client, token: str) -> dict:
    return {b["id"]: b for b in client.get("/api/p/state", headers=tok(token)).json()["boxes"]}


def test_lobby_shows_titles_only(admin_client):
    run = open_run(admin_client)
    p = join(admin_client, run["entry_code"], "가")
    view = admin_client.get("/api/p/state", headers=tok(p["token"])).json()
    assert view["run"]["status"] == "lobby"
    assert view["me"] == {"id": p["participant_id"], "name": "가", "assigned_box_id": None, "is_leader": False}
    assert [b["id"] for b in view["boxes"]] == ["story", "team", "result"]
    assert all("markdown" not in b for b in view["boxes"])


def test_personal_boxes_of_others_are_hidden(admin_client):
    ctx = started_parking_run(admin_client)
    boxes = boxes_of(admin_client, ctx["tokens"]["a"])
    assert list(boxes) == ["story", "a", "team", "result"]
    assert boxes["a"]["state"] == "open"
    assert boxes["a"]["markdown"] == "입차 문제"
    assert boxes["a"]["editor_files"] == [{"name": "a_entry.py", "starter": "# a_entry.py\n"}]
    assert boxes["story"]["state"] == "closed" and boxes["story"]["markdown"] == "스토리 문제"
    assert "markdown" not in boxes["team"]


def test_admin_edits_problem_text_live(admin_client):
    ctx = started_parking_run(admin_client)
    r = admin_client.patch(f"/api/runs/{ctx['run']['id']}/boxes/a", json={"markdown": "고친 문제"})
    assert r.status_code == 200
    assert boxes_of(admin_client, ctx["tokens"]["a"])["a"]["markdown"] == "고친 문제"
    assert admin_client.patch(f"/api/runs/{ctx['run']['id']}/boxes/zz", json={"markdown": "x"}).status_code == 404


def test_attachment_visibility(admin_client):
    t = create_template(admin_client)
    admin_client.post(f"/api/templates/{t['id']}/files", data={"box_id": "a"}, files={"file": ("a_예제.py", b"A")})
    run = open_run(admin_client, t["id"])
    pa = join(admin_client, run["entry_code"], "가")
    pb = join(admin_client, run["entry_code"], "나")
    assign(admin_client, run["id"], pa["participant_id"], "a")
    assign(admin_client, run["id"], pb["participant_id"], "b")

    file_id = admin_client.get(f"/api/runs/{run['id']}/state").json()["files"]["a"][0]["id"]
    # 시작 전에는 박스가 잠겨 있어 받을 수 없다
    assert admin_client.get(f"/api/p/files/{file_id}", headers=tok(pa["token"])).status_code == 404
    admin_client.post(f"/api/runs/{run['id']}/start")
    assert boxes_of(admin_client, pa["token"])["a"]["attachments"] == [{"id": file_id, "filename": "a_예제.py", "size": 1}]
    assert admin_client.get(f"/api/p/files/{file_id}", headers=tok(pa["token"])).content == b"A"
    assert admin_client.get(f"/api/p/files/{file_id}", headers=tok(pb["token"])).status_code == 404
