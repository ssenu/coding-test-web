from tests.helpers import approve_all, assign, join, open_run, started_parking_run, submit, tok


def test_resubmit_keeps_last(admin_client):
    ctx = started_parking_run(admin_client)
    assert submit(admin_client, ctx["tokens"]["a"], "a", "v1").status_code == 200
    assert submit(admin_client, ctx["tokens"]["a"], "a", "v2").status_code == 200
    sub = admin_client.get(f"/api/runs/{ctx['run']['id']}/boxes/a/submission").json()
    assert sub["files"] == {"a_entry.py": "v2"}
    assert sub["participant_id"] == ctx["ids"]["a"]
    state = admin_client.get(f"/api/runs/{ctx['run']['id']}/state").json()
    assert set(state["submissions"]) == {"a"}


def test_submit_rules(admin_client):
    ctx = started_parking_run(admin_client)
    a = tok(ctx["tokens"]["a"])
    assert submit(admin_client, ctx["tokens"]["a"], "b").status_code == 403
    wrong = admin_client.post("/api/p/boxes/a/submit", json={"files": {"other.py": ""}}, headers=a)
    assert wrong.status_code == 422
    big = admin_client.post("/api/p/boxes/a/submit", json={"files": {"a_entry.py": "x" * (200 * 1024 + 1)}}, headers=a)
    assert big.status_code == 413
    assert admin_client.post("/api/p/boxes/nope/submit", json={"files": {}}, headers=a).status_code == 404


def test_submit_before_start_rejected(admin_client):
    run = open_run(admin_client)
    p = join(admin_client, run["entry_code"], "가")
    assign(admin_client, run["id"], p["participant_id"], "a")
    assert submit(admin_client, p["token"], "a").status_code == 409


def test_approval_asks_confirm_when_unsubmitted(admin_client):
    ctx = started_parking_run(admin_client)
    run_id = ctx["run"]["id"]
    submit(admin_client, ctx["tokens"]["a"], "a", "A")
    r = approve_all(admin_client, run_id, confirm=False)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "unsubmitted"
    assert r.json()["detail"]["box_ids"] == ["b", "c", "d"]
    assert admin_client.get(f"/api/runs/{run_id}/state").json()["boxes"]["team"]["state"] == "locked"

    r = approve_all(admin_client, run_id, confirm=True)
    assert r.status_code == 200
    boxes = r.json()["boxes"]
    assert boxes["team"]["state"] == "open"
    assert [boxes[x]["state"] for x in "abcd"] == ["closed"] * 4
    assert r.json()["approved_edges"] == ["a-team", "b-team", "c-team", "d-team"]


def test_submit_after_close_rejected(admin_client):
    ctx = started_parking_run(admin_client)
    approve_all(admin_client, ctx["run"]["id"])
    r = submit(admin_client, ctx["tokens"]["a"], "a")
    assert r.status_code == 409
    assert r.json()["detail"] == "이 단계는 닫혔습니다."


def test_partial_approval_and_idempotency(admin_client):
    ctx = started_parking_run(admin_client)
    run_id = ctx["run"]["id"]
    body = {"edge_ids": ["a-team", "b-team"], "confirm": True}
    assert admin_client.post(f"/api/runs/{run_id}/approvals", json=body).status_code == 200
    again = admin_client.post(f"/api/runs/{run_id}/approvals", json=body)
    assert again.status_code == 200
    assert again.json()["boxes"]["team"]["state"] == "locked"
    assert again.json()["approved_edges"] == ["a-team", "b-team"]


def test_approve_rejects_auto_edge_and_unknown(admin_client):
    ctx = started_parking_run(admin_client)
    run_id = ctx["run"]["id"]
    assert admin_client.post(f"/api/runs/{run_id}/approvals", json={"edge_ids": ["s-a"]}).status_code == 404
    assert admin_client.post(f"/api/runs/{run_id}/approvals", json={"edge_ids": ["zz"]}).status_code == 404


def test_approve_before_start_rejected(admin_client):
    run = open_run(admin_client)
    assert approve_all(admin_client, run["id"]).status_code == 409


def test_my_submission_in_state(admin_client):
    ctx = started_parking_run(admin_client)
    submit(admin_client, ctx["tokens"]["a"], "a", "A")
    view = admin_client.get("/api/p/state", headers=tok(ctx["tokens"]["a"])).json()
    assert view["my_submission"]["files"] == {"a_entry.py": "A"}
    other = admin_client.get("/api/p/state", headers=tok(ctx["tokens"]["b"])).json()
    assert other["my_submission"] is None
