"""테스트용 시험장 그래프. 주차장 과제 구조: 스토리 → 개인 A~D(자동) → 팀(승인) → 결과(자동)."""


def box(box_id: str, box_type: str, title: str, files: tuple[str, ...] = ()) -> dict:
    return {
        "id": box_id,
        "type": box_type,
        "title": title,
        "position": {"x": 0, "y": 0},
        "config": {
            "markdown": f"{title} 문제",
            "attachments_enabled": False,
            "editor": {"files": [{"name": n, "starter": f"# {n}\n"} for n in files]},
        },
    }


def parking_graph_dict() -> dict:
    boxes = [
        box("story", "common", "스토리"),
        box("a", "personal", "입차", ("a_entry.py",)),
        box("b", "personal", "출차", ("b_exit.py",)),
        box("c", "personal", "요금", ("c_fee.py",)),
        box("d", "personal", "현황", ("d_status.py",)),
        box("team", "team", "통합", ("e_main.py",)),
        box("result", "result", "결과"),
    ]
    edges = [{"id": f"s-{x}", "source": "story", "target": x, "mode": "auto"} for x in "abcd"]
    edges += [{"id": f"{x}-team", "source": x, "target": "team", "mode": "approval"} for x in "abcd"]
    edges.append({"id": "team-result", "source": "team", "target": "result", "mode": "auto"})
    return {"boxes": boxes, "edges": edges}
