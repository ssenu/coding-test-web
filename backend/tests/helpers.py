"""API 테스트 공용 도우미."""
from tests.graphs import parking_graph_dict

PARKING_FILES = {"a": "a_entry.py", "b": "b_exit.py", "c": "c_fee.py", "d": "d_status.py"}
APPROVAL_EDGES = ["a-team", "b-team", "c-team", "d-team"]


def tok(token: str) -> dict:
    return {"X-Participant-Token": token}


def create_template(client, graph: dict | None = None, name: str = "주차장") -> dict:
    r = client.post(
        "/api/templates",
        json={"name": name, "graph": graph if graph is not None else parking_graph_dict()},
    )
    assert r.status_code == 201, r.text
    return r.json()


def open_run(client, template_id: int | None = None) -> dict:
    if template_id is None:
        template_id = create_template(client)["id"]
    r = client.post(f"/api/templates/{template_id}/runs", json={"name": "1기"})
    assert r.status_code == 201, r.text
    return r.json()


def join(client, entry_code: str, name: str) -> dict:
    r = client.post("/api/p/join", json={"entry_code": entry_code, "name": name})
    assert r.status_code == 200, r.text
    return r.json()


def assign(client, run_id: int, participant_id: int, box_id: str | None, leader: bool = False) -> None:
    body: dict = {"assigned_box_id": box_id}
    if leader:
        body["is_leader"] = True
    r = client.patch(f"/api/runs/{run_id}/participants/{participant_id}", json=body)
    assert r.status_code == 200, r.text


def started_parking_run(client) -> dict:
    """주차장 회차를 열고 4명을 입장·배정(a가 팀장)한 뒤 시작한다."""
    run = open_run(client)
    tokens: dict[str, str] = {}
    ids: dict[str, int] = {}
    for box_id in "abcd":
        joined = join(client, run["entry_code"], f"참가자{box_id}")
        tokens[box_id], ids[box_id] = joined["token"], joined["participant_id"]
        assign(client, run["id"], joined["participant_id"], box_id, leader=(box_id == "a"))
    r = client.post(f"/api/runs/{run['id']}/start")
    assert r.status_code == 200, r.text
    return {"run": run, "tokens": tokens, "ids": ids}


def submit(client, token: str, box_id: str, code: str = "print('hi')\n"):
    return client.post(
        f"/api/p/boxes/{box_id}/submit",
        json={"files": {PARKING_FILES[box_id]: code}},
        headers=tok(token),
    )


def approve_all(client, run_id: int, confirm: bool = True):
    return client.post(
        f"/api/runs/{run_id}/approvals", json={"edge_ids": APPROVAL_EDGES, "confirm": confirm}
    )
