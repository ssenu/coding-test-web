from app.engine.flow import CLOSED, LOCKED, OPEN, FlowState, advance, can_approve, seed_team_files
from app.engine.graph import parse_graph
from tests.graphs import box, parking_graph_dict

GRAPH = parse_graph(parking_graph_dict())


def apply(states: dict, tr) -> dict:
    new = dict(states)
    for b in tr.opened:
        new[b] = OPEN
    for b in tr.closed:
        new[b] = CLOSED
    return new


def started() -> dict:
    locked = {b: LOCKED for b in GRAPH.boxes}
    return apply(locked, advance(GRAPH, FlowState(locked)))


def test_start_opens_story_then_personal_boxes():
    locked = {b: LOCKED for b in GRAPH.boxes}
    tr = advance(GRAPH, FlowState(locked))
    assert tr.opened == ("story", "a", "b", "c", "d")
    assert tr.closed == ("story",)
    assert not tr.finished


def test_submission_alone_does_not_open_approval_gate():
    tr = advance(GRAPH, FlowState(started(), submitted=frozenset("abcd")))
    assert not tr.changed


def test_partial_approval_keeps_team_locked():
    tr = advance(GRAPH, FlowState(started(), approved=frozenset({"a-team", "b-team", "c-team"})))
    assert not tr.changed


def test_full_approval_opens_team_and_closes_personal():
    tr = advance(GRAPH, FlowState(started(), approved=frozenset({"a-team", "b-team", "c-team", "d-team"})))
    assert tr.opened == ("team",)
    assert set(tr.closed) == {"a", "b", "c", "d"}


def test_team_final_opens_result_and_finishes():
    states = started()
    states.update({x: CLOSED for x in "abcd"}, team=OPEN)
    tr = advance(GRAPH, FlowState(states, final_team=frozenset({"team"})))
    assert tr.opened == ("result",)
    assert tr.closed == ("team",)
    assert tr.finished


def test_can_approve():
    edge = GRAPH.edge("a-team")
    locked = {b: LOCKED for b in GRAPH.boxes}
    assert not can_approve(edge, locked)
    assert can_approve(edge, started())
    assert not can_approve(GRAPH.edge("s-a"), started())  # 자동 선은 승인 대상이 아님


def test_seed_team_files_prefers_submissions():
    files = seed_team_files(GRAPH, "team", {"a": {"a_entry.py": "A"}})
    assert files == {
        "a_entry.py": "A",
        "b_exit.py": "# b_exit.py\n",
        "c_fee.py": "# c_fee.py\n",
        "d_status.py": "# d_status.py\n",
        "e_main.py": "# e_main.py\n",
    }
    assert list(files)[-1] == "e_main.py"


def test_seed_team_files_name_clash_submission_wins():
    data = parking_graph_dict()
    team = next(b for b in data["boxes"] if b["id"] == "team")
    team["config"]["editor"]["files"].append({"name": "a_entry.py", "starter": "TEAM"})
    graph = parse_graph(data)
    assert seed_team_files(graph, "team", {"a": {"a_entry.py": "MINE"}})["a_entry.py"] == "MINE"


def test_multiple_start_boxes():
    data = {
        "boxes": [box("s1", "common", "1"), box("s2", "common", "2"), box("r", "result", "r")],
        "edges": [
            {"id": "1", "source": "s1", "target": "r", "mode": "auto"},
            {"id": "2", "source": "s2", "target": "r", "mode": "auto"},
        ],
    }
    graph = parse_graph(data)
    tr = advance(graph, FlowState({b: LOCKED for b in graph.boxes}))
    assert tr.opened == ("s1", "s2", "r")
    assert tr.finished
