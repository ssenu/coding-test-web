from tests.helpers import approve_all, started_parking_run, submit, tok


def team_ready(client) -> dict:
    ctx = started_parking_run(client)
    submit(client, ctx["tokens"]["a"], "a", "A")
    submit(client, ctx["tokens"]["b"], "b", "B")
    approve_all(client, ctx["run"]["id"])
    return ctx


def team_files(client, token: str) -> dict:
    return client.get("/api/p/state", headers=tok(token)).json()["team"]["team"]["files"]


def test_team_box_seeded_with_submissions(admin_client):
    ctx = team_ready(admin_client)
    files = team_files(admin_client, ctx["tokens"]["c"])
    assert files == {
        "a_entry.py": "A",
        "b_exit.py": "B",
        "c_fee.py": "# c_fee.py\n",
        "d_status.py": "# d_status.py\n",
        "e_main.py": "# e_main.py\n",
    }


def test_only_leader_edits(admin_client):
    ctx = team_ready(admin_client)
    files = team_files(admin_client, ctx["tokens"]["a"])
    r = admin_client.put("/api/p/boxes/team/draft", json={"files": files}, headers=tok(ctx["tokens"]["b"]))
    assert r.status_code == 403
    files["a_entry.py"] = "A2"
    r = admin_client.put("/api/p/boxes/team/draft", json={"files": files}, headers=tok(ctx["tokens"]["a"]))
    assert r.status_code == 200
    assert team_files(admin_client, ctx["tokens"]["b"])["a_entry.py"] == "A2"


def test_draft_rejects_new_file_names(admin_client):
    ctx = team_ready(admin_client)
    files = {**team_files(admin_client, ctx["tokens"]["a"]), "extra.py": ""}
    r = admin_client.put("/api/p/boxes/team/draft", json={"files": files}, headers=tok(ctx["tokens"]["a"]))
    assert r.status_code == 422


def test_versions_and_final_submit_finish_run(admin_client):
    ctx = team_ready(admin_client)
    run_id = ctx["run"]["id"]
    leader = tok(ctx["tokens"]["a"])
    files = team_files(admin_client, ctx["tokens"]["a"])

    v1 = admin_client.post("/api/p/boxes/team/versions", json={"files": files}, headers=leader)
    assert v1.status_code == 201
    assert (v1.json()["version_no"], v1.json()["is_final"]) == (1, False)
    assert admin_client.get(f"/api/runs/{run_id}/state").json()["run"]["status"] == "running"

    files["e_main.py"] = "print('done')\n"
    v2 = admin_client.post("/api/p/boxes/team/versions", json={"files": files, "final": True}, headers=leader)
    assert (v2.json()["version_no"], v2.json()["is_final"]) == (2, True)

    state = admin_client.get(f"/api/runs/{run_id}/state").json()
    assert state["run"]["status"] == "finished"
    assert state["boxes"]["result"]["state"] == "open"
    assert state["boxes"]["team"]["state"] == "closed"
    assert [v["version_no"] for v in state["team_versions"]["team"]] == [1, 2]

    versions = admin_client.get(f"/api/runs/{run_id}/boxes/team/versions").json()
    detail = admin_client.get(f"/api/runs/{run_id}/versions/{versions[1]['id']}").json()
    assert detail["files"]["e_main.py"] == "print('done')\n"

    member_view = admin_client.get("/api/p/state", headers=tok(ctx["tokens"]["d"])).json()
    assert member_view["result"]["team"]["e_main.py"] == "print('done')\n"
    assert member_view["team"]["team"]["final"]["version_no"] == 2

    again = admin_client.put("/api/p/boxes/team/draft", json={"files": files}, headers=leader)
    assert again.status_code == 409
