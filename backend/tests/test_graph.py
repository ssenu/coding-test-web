import pytest

from app.engine.graph import GraphError, parse_graph, validate_graph
from tests.graphs import box, parking_graph_dict


def messages(data: dict) -> list[str]:
    return [i.message for i in validate_graph(parse_graph(data))]


def test_parking_graph_is_valid():
    graph = parse_graph(parking_graph_dict())
    assert validate_graph(graph) == []
    assert graph.start_boxes() == ["story"]
    assert graph.boxes["a"].files[0].name == "a_entry.py"
    assert graph.ancestors("team") == {"story", "a", "b", "c", "d"}
    assert graph.edge("a-team").mode == "approval"


@pytest.mark.parametrize(
    "data",
    [
        "not a dict",
        {"boxes": [{"id": "x"}]},
        {"boxes": [box("x", "weird", "?")]},
        {"boxes": [box("x", "common", "1"), box("x", "common", "2")]},
        {"boxes": [box("x", "common", "1")], "edges": [{"id": "e", "source": "x", "target": "nope"}]},
        {"boxes": [box("x", "common", "1")], "edges": [{"id": "e", "source": "x", "target": "x"}]},
        {"boxes": [box("x", "common", "1"), box("y", "result", "2")],
         "edges": [{"id": "e", "source": "x", "target": "y", "mode": "later"}]},
        {"boxes": [box("p", "personal", "p", ("a.py", "a.py"))]},
        {"boxes": None},
        {"boxes": "ab"},
        {"boxes": [], "edges": None},
        {"boxes": [dict(box("x", "common", "1"), config="x")]},
        {"boxes": [dict(box("x", "common", "1"), config={"editor": []})]},
        {"boxes": [dict(box("p", "personal", "p"), config={"editor": {"files": "a.py"}})]},
    ],
)
def test_parse_rejects_malformed(data):
    with pytest.raises(GraphError):
        parse_graph(data)


def test_empty_graph():
    assert messages({"boxes": [], "edges": []}) == ["박스가 하나도 없습니다."]


def test_too_many_personal_boxes():
    data = {
        "boxes": [box(f"p{i}", "personal", str(i), ("x.py",)) for i in range(7)] + [box("r", "result", "r")],
        "edges": [{"id": f"e{i}", "source": f"p{i}", "target": "r", "mode": "auto"} for i in range(7)],
    }
    assert "개인 박스는 6개까지 둘 수 있습니다." in messages(data)


def test_result_box_count():
    data = {"boxes": [box("s", "common", "s")], "edges": []}
    assert "결과 박스는 정확히 1개 있어야 합니다." in messages(data)


def test_personal_box_needs_files():
    data = {
        "boxes": [box("p", "personal", "p"), box("r", "result", "r")],
        "edges": [{"id": "e", "source": "p", "target": "r", "mode": "auto"}],
    }
    issues = validate_graph(parse_graph(data))
    assert any(i.box_ids == ("p",) and "코드 파일" in i.message for i in issues)


def test_cycle_detected():
    data = {
        "boxes": [box("s", "common", "s"), box("a", "common", "a"), box("b", "common", "b"), box("r", "result", "r")],
        "edges": [
            {"id": "1", "source": "s", "target": "a", "mode": "auto"},
            {"id": "2", "source": "a", "target": "b", "mode": "auto"},
            {"id": "3", "source": "b", "target": "a", "mode": "auto"},
            {"id": "4", "source": "b", "target": "r", "mode": "auto"},
        ],
    }
    issues = validate_graph(parse_graph(data))
    cycle = next(i for i in issues if i.message == "순환 연결이 있습니다.")
    assert set(cycle.box_ids) == {"a", "b", "r"}


def test_stranded_box():
    data = parking_graph_dict()
    data["boxes"].append(box("lonely", "common", "외톨이"))
    issues = validate_graph(parse_graph(data))
    assert any(i.box_ids == ("lonely",) for i in issues)


def test_result_box_cannot_have_outgoing():
    data = {
        "boxes": [box("s", "common", "s"), box("r", "result", "r"), box("x", "common", "x")],
        "edges": [
            {"id": "1", "source": "s", "target": "r", "mode": "auto"},
            {"id": "2", "source": "r", "target": "x", "mode": "auto"},
        ],
    }
    assert "결과 박스에서 나가는 연결선은 둘 수 없습니다." in messages(data)
