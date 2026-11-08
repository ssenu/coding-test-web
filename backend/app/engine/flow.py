"""박스 열림 규칙. DB와 무관한 순수 함수."""
from __future__ import annotations

from dataclasses import dataclass

from app.engine.graph import Edge, Graph

LOCKED, OPEN, CLOSED = "locked", "open", "closed"


@dataclass(frozen=True)
class FlowState:
    states: dict[str, str]                       # box_id -> locked/open/closed
    submitted: frozenset[str] = frozenset()      # 제출본이 있는 개인 박스
    final_team: frozenset[str] = frozenset()     # 최종 제출된 팀 박스
    approved: frozenset[str] = frozenset()       # 승인된 연결선


@dataclass(frozen=True)
class Transition:
    opened: tuple[str, ...]
    closed: tuple[str, ...]
    finished: bool

    @property
    def changed(self) -> bool:
        return bool(self.opened or self.closed)


def is_complete(graph: Graph, box_id: str, fs: FlowState) -> bool:
    if fs.states.get(box_id, LOCKED) == LOCKED:
        return False
    box_type = graph.boxes[box_id].type
    if box_type == "common":
        return True
    if box_type == "personal":
        return box_id in fs.submitted
    if box_type == "team":
        return box_id in fs.final_team
    return False


def edge_satisfied(graph: Graph, edge: Edge, fs: FlowState) -> bool:
    if fs.states.get(edge.source, LOCKED) == LOCKED:
        return False
    if edge.mode == "approval":
        return edge.id in fs.approved
    return is_complete(graph, edge.source, fs)


def can_approve(edge: Edge, states: dict[str, str]) -> bool:
    """출발 박스가 열린 적이 있고 도착 박스가 아직 잠겨 있으면 승인할 수 있다."""
    return (
        edge.mode == "approval"
        and states.get(edge.source, LOCKED) != LOCKED
        and states.get(edge.target, LOCKED) == LOCKED
    )


def advance(graph: Graph, fs: FlowState) -> Transition:
    """열 수 있는 박스를 더 이상 없을 때까지 연다. 박스가 열리면 들어오는 선의 출발 박스는 닫힌다."""
    states = dict(fs.states)
    opened: list[str] = []
    closed: list[str] = []
    progress = True
    while progress:
        progress = False
        current = FlowState(states, fs.submitted, fs.final_team, fs.approved)
        for box_id in graph.boxes:
            if states.get(box_id, LOCKED) != LOCKED:
                continue
            incoming = graph.incoming(box_id)
            if all(edge_satisfied(graph, e, current) for e in incoming):
                states[box_id] = OPEN
                opened.append(box_id)
                for e in incoming:
                    if states.get(e.source) == OPEN:
                        states[e.source] = CLOSED
                        closed.append(e.source)
                progress = True
                break
    finished = any(
        b.type == "result" and states.get(b.id) == OPEN for b in graph.boxes.values()
    )
    return Transition(tuple(opened), tuple(closed), finished)


def seed_team_files(
    graph: Graph, team_id: str, submissions: dict[str, dict[str, str]]
) -> dict[str, str]:
    """팀 박스가 열릴 때의 파일. 앞 개인 박스 제출본(없으면 시작 코드) + 팀 박스 시작 코드.
    같은 이름이면 개인 박스 쪽이 이긴다."""
    ancestors = graph.ancestors(team_id)
    files: dict[str, str] = {}
    for box in graph.boxes.values():
        if box.id not in ancestors or box.type != "personal":
            continue
        if box.id in submissions:
            files.update(submissions[box.id])
        else:
            files.update({f.name: f.starter for f in box.files})
    for f in graph.boxes[team_id].files:
        files.setdefault(f.name, f.starter)
    return files
