"""시험장 그래프(박스와 연결선)의 구조와 저장 전 검사. DB와 무관한 순수 코드."""
from __future__ import annotations

from dataclasses import dataclass

BOX_TYPES = ("common", "personal", "team", "result")
EDGE_MODES = ("auto", "approval")
MAX_PERSONAL_BOXES = 6


class GraphError(ValueError):
    """그래프 JSON의 모양 자체가 잘못됐을 때."""


@dataclass(frozen=True)
class EditorFile:
    name: str
    starter: str = ""


@dataclass(frozen=True)
class Box:
    id: str
    type: str
    title: str
    markdown: str = ""
    attachments_enabled: bool = False
    files: tuple[EditorFile, ...] = ()


@dataclass(frozen=True)
class Edge:
    id: str
    source: str
    target: str
    mode: str


@dataclass(frozen=True)
class Issue:
    message: str
    box_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Graph:
    boxes: dict[str, Box]
    edges: tuple[Edge, ...]

    def incoming(self, box_id: str) -> list[Edge]:
        return [e for e in self.edges if e.target == box_id]

    def outgoing(self, box_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == box_id]

    def edge(self, edge_id: str) -> Edge | None:
        return next((e for e in self.edges if e.id == edge_id), None)

    def start_boxes(self) -> list[str]:
        return [b for b in self.boxes if not self.incoming(b)]

    def ancestors(self, box_id: str) -> set[str]:
        """box_id로 이어지는 모든 앞 박스."""
        seen: set[str] = set()
        frontier = [e.source for e in self.incoming(box_id)]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(e.source for e in self.incoming(current))
        return seen


def _parse_files(raw_box: dict) -> tuple[EditorFile, ...]:
    config = raw_box.get("config") or {}
    editor = config.get("editor") or {}
    files: list[EditorFile] = []
    names: set[str] = set()
    for raw in editor.get("files", []):
        name = str(raw.get("name", "")).strip() if isinstance(raw, dict) else ""
        if not name:
            raise GraphError(f"박스 {raw_box.get('id')}의 코드 파일에 이름이 없습니다.")
        if name in names:
            raise GraphError(f"박스 {raw_box.get('id')}에 같은 파일 이름이 두 번 있습니다: {name}")
        names.add(name)
        files.append(EditorFile(name=name, starter=str(raw.get("starter", ""))))
    return tuple(files)


def parse_graph(data: dict) -> Graph:
    """JSON(dict)을 Graph로 바꾼다. 모양이 잘못됐으면 GraphError."""
    if not isinstance(data, dict):
        raise GraphError("그래프는 객체여야 합니다.")
    boxes: dict[str, Box] = {}
    for raw in data.get("boxes", []):
        if not isinstance(raw, dict) or "id" not in raw or "type" not in raw:
            raise GraphError("박스에 id와 type이 필요합니다.")
        box_id, box_type = str(raw["id"]), raw["type"]
        if box_type not in BOX_TYPES:
            raise GraphError(f"알 수 없는 박스 종류입니다: {box_type}")
        if box_id in boxes:
            raise GraphError(f"박스 id가 겹칩니다: {box_id}")
        config = raw.get("config") or {}
        boxes[box_id] = Box(
            id=box_id,
            type=box_type,
            title=str(raw.get("title", "")),
            markdown=str(config.get("markdown", "")),
            attachments_enabled=bool(config.get("attachments_enabled", False)),
            files=_parse_files(raw),
        )
    edges: list[Edge] = []
    edge_ids: set[str] = set()
    for raw in data.get("edges", []):
        if not isinstance(raw, dict) or not {"id", "source", "target"} <= raw.keys():
            raise GraphError("연결선에 id, source, target이 필요합니다.")
        edge = Edge(
            id=str(raw["id"]),
            source=str(raw["source"]),
            target=str(raw["target"]),
            mode=raw.get("mode", "approval"),
        )
        if edge.mode not in EDGE_MODES:
            raise GraphError(f"알 수 없는 연결선 방식입니다: {edge.mode}")
        if edge.source not in boxes or edge.target not in boxes:
            raise GraphError(f"연결선 {edge.id}이 없는 박스를 가리킵니다.")
        if edge.source == edge.target:
            raise GraphError(f"연결선 {edge.id}이 자기 자신을 가리킵니다.")
        if edge.id in edge_ids:
            raise GraphError(f"연결선 id가 겹칩니다: {edge.id}")
        edge_ids.add(edge.id)
        edges.append(edge)
    return Graph(boxes=boxes, edges=tuple(edges))


def _cycle_boxes(graph: Graph) -> tuple[str, ...]:
    indegree = {b: 0 for b in graph.boxes}
    for e in graph.edges:
        indegree[e.target] += 1
    queue = [b for b, d in indegree.items() if d == 0]
    removed: set[str] = set()
    while queue:
        current = queue.pop()
        removed.add(current)
        for e in graph.outgoing(current):
            indegree[e.target] -= 1
            if indegree[e.target] == 0:
                queue.append(e.target)
    return tuple(b for b in graph.boxes if b not in removed)


def _reaching(graph: Graph, target: str) -> set[str]:
    reach = {target}
    frontier = [target]
    while frontier:
        current = frontier.pop()
        for e in graph.incoming(current):
            if e.source not in reach:
                reach.add(e.source)
                frontier.append(e.source)
    return reach


def validate_graph(graph: Graph) -> list[Issue]:
    """회차를 열 수 있는 그래프인지 검사한다. 문제가 없으면 빈 리스트."""
    if not graph.boxes:
        return [Issue("박스가 하나도 없습니다.")]
    issues: list[Issue] = []
    personal = tuple(b.id for b in graph.boxes.values() if b.type == "personal")
    if len(personal) > MAX_PERSONAL_BOXES:
        issues.append(Issue(f"개인 박스는 {MAX_PERSONAL_BOXES}개까지 둘 수 있습니다.", personal))
    results = tuple(b.id for b in graph.boxes.values() if b.type == "result")
    if len(results) != 1:
        issues.append(Issue("결과 박스는 정확히 1개 있어야 합니다.", results))
    for result_id in results:
        if graph.outgoing(result_id):
            issues.append(Issue("결과 박스에서 나가는 연결선은 둘 수 없습니다.", (result_id,)))
    no_files = tuple(
        b.id for b in graph.boxes.values() if b.type in ("personal", "team") and not b.files
    )
    if no_files:
        issues.append(Issue("개인 박스와 팀 박스에는 코드 파일이 1개 이상 필요합니다.", no_files))
    cycle = _cycle_boxes(graph)
    if cycle:
        issues.append(Issue("순환 연결이 있습니다.", cycle))
    if not graph.start_boxes():
        issues.append(Issue("시작 박스(들어오는 연결선이 없는 박스)가 없습니다."))
    if len(results) == 1:
        reach = _reaching(graph, results[0])
        stranded = tuple(b for b in graph.boxes if b not in reach)
        if stranded:
            issues.append(Issue("결과 박스까지 이어지지 않는 박스가 있습니다.", stranded))
    return issues
