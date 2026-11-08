"""주차장 과제로 회차 하나를 처음부터 끝까지 진행한다."""
from tests.helpers import PARKING_FILES, assign, create_template, join, open_run, tok


def test_full_parking_run(admin_client):
    c = admin_client
    template = create_template(c)
    run = open_run(c, template["id"])
    run_id = run["id"]

    people = {box: join(c, run["entry_code"], name) for box, name in zip("abcd", ["가", "나", "다", "라"])}
    for box, joined in people.items():
        assign(c, run_id, joined["participant_id"], box, leader=(box == "c"))

    c.post(f"/api/runs/{run_id}/start")
    for box, joined in people.items():
        r = c.post(
            f"/api/p/boxes/{box}/submit",
            json={"files": {PARKING_FILES[box]: f"# {box} 완료\n"}},
            headers=tok(joined["token"]),
        )
        assert r.status_code == 200, r.text

    state = c.get(f"/api/runs/{run_id}/state").json()
    assert set(state["submissions"]) == {"a", "b", "c", "d"}
    approve = c.post(f"/api/runs/{run_id}/approvals", json={"edge_ids": ["a-team", "b-team", "c-team", "d-team"]})
    assert approve.status_code == 200, approve.text

    leader = tok(people["c"]["token"])
    files = c.get("/api/p/state", headers=leader).json()["team"]["team"]["files"]
    assert files["a_entry.py"] == "# a 완료\n"
    files["a_entry.py"] += "# 팀에서 고침\n"
    files["e_main.py"] = "from a_entry import car_in\n"
    final = c.post("/api/p/boxes/team/versions", json={"files": files, "final": True}, headers=leader)
    assert final.status_code == 201

    state = c.get(f"/api/runs/{run_id}/state").json()
    assert state["run"]["status"] == "finished"
    version_id = state["team_versions"]["team"][-1]["id"]
    result = c.get(f"/api/runs/{run_id}/versions/{version_id}").json()
    assert result["files"]["a_entry.py"] == "# a 완료\n# 팀에서 고침\n"
    assert result["files"]["e_main.py"] == "from a_entry import car_in\n"
