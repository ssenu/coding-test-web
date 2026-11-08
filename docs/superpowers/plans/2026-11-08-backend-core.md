# 백엔드 코어 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설계 문서(`docs/superpowers/specs/2026-11-08-coding-test-web-design.md`)의 서버 쪽 전부(시험장, 회차, 박스 열림 규칙, 참가자 입장, 제출, 승인, 팀 단계, 실시간 알림)를 FastAPI로 구현하고 테스트로 검증한다.

**Architecture:** 박스 열림 규칙은 DB와 무관한 순수 함수(`app/engine`)로 두고, 서비스 계층(`app/services`)이 DB 상태를 읽어 엔진을 돌린 뒤 결과를 저장하고 웹소켓 허브로 알린다. 상태 변경은 모두 REST로 받고, DB 커밋 다음에 이벤트를 보낸다. 앱은 `create_app(settings)` 팩토리로 만들어 테스트마다 임시 디렉터리의 SQLite를 쓴다.

**Tech Stack:** Python 3.12+, FastAPI, SQLModel(SQLite), itsdangerous, python-multipart, uvicorn; 테스트는 pytest + FastAPI TestClient.

## 이 계획의 범위

설계를 세 계획으로 나눈다. 이 문서는 첫 번째다.

1. **백엔드 코어 (이 문서)** — 끝나면 API와 웹소켓이 모두 동작하고, 주차장 시나리오가 테스트로 끝까지 돈다.
2. 프런트엔드 (Vue 3 + Vue Flow + CodeMirror) — 이 계획의 API 위에서 만든다.
3. 배포와 마무리 — Dockerfile, docker-compose, 정적 파일 서빙, Alembic 기준 마이그레이션, 주차장 시드, Playwright 전체 흐름.

## Global Constraints

- Python `>=3.12`, `sqlmodel>=0.0.48`(timezone 있는 datetime 필수), `fastapi>=0.115`.
- uvicorn 워커는 1개(`--workers 1`). 웹소켓 연결과 입장 시도 제한을 메모리에 둔다.
- 시각은 timezone이 붙은 UTC `datetime`. API로는 `iso()`로 `...Z` 문자열을 내보낸다.
- 한 회차의 개인 박스는 최대 6개(`MAX_PERSONAL_BOXES = 6`).
- 코드 파일 하나 200KB(`MAX_CODE_BYTES`), 첨부 파일 하나 10MB(`MAX_ATTACHMENT_BYTES`).
- 참가자 인증 헤더 `X-Participant-Token`, 관리자 쿠키 `admin_session`(HttpOnly, SameSite=Lax, `COOKIE_SECURE=1`이면 Secure).
- 제출 코드는 실행하지 않는다. 텍스트로만 저장·전달한다.
- 사용자에게 보이는 오류 메시지(`detail`)는 한국어.
- 모든 명령은 `backend/`에서, 가상환경을 활성화한 상태로 실행한다(Windows Git Bash: `source .venv/Scripts/activate`, macOS/Linux: `source .venv/bin/activate`).

## 파일 구조

```
backend/
  pyproject.toml
  README.md
  app/
    config.py          설정(환경변수)
    main.py            create_app 팩토리
    models.py          SQLModel 테이블, utcnow/iso
    db.py              엔진 생성, 테이블 생성
    auth.py            관리자 쿠키, 참가자 토큰
    deps.py            FastAPI 의존성(세션, 설정, 허브, 인증)
    storage.py         첨부 파일 저장/복사/삭제
    ratelimit.py       입장 시도 제한
    engine/graph.py    그래프 파싱과 저장 전 검사 (순수)
    engine/flow.py     박스 열림 규칙 (순수)
    services/runs.py   회차 상태 읽기, 엔진 적용, 알림
    services/progress.py  제출, 승인, 팀 편집
    services/views.py  API 응답 묶음, 참가자용 필터링
    ws/hub.py          회차별 웹소켓 연결과 발송
    api/admin.py       로그인
    api/templates.py   시험장 CRUD, 첨부 파일
    api/runs.py        회차 관리(관리자)
    api/participant.py 참가자 API
    api/ws.py          웹소켓 엔드포인트
  tests/
    conftest.py, graphs.py, helpers.py, test_*.py
```

---

### Task 1: 백엔드 뼈대: 설정과 헬스 체크

FastAPI 앱 팩토리와 환경변수 설정을 만든다. 이후 모든 작업이 `create_app(settings)`로 테스트용 앱을 만든다.

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `app.config.Settings(admin_password: str, secret_key: str, data_dir: Path, cookie_secure: bool = False)` — 속성 `db_url`, `files_dir`
  - `app.config.load_settings() -> Settings` — 환경변수 `ADMIN_PASSWORD`, `SECRET_KEY`(필수), `DATA_DIR`(기본 `/data`), `COOKIE_SECURE`(`1`이면 True)
  - `app.main.create_app(settings: Settings | None = None) -> FastAPI`
  - pytest 픽스처 `settings`, `app`, `client`(`tests/conftest.py`)

- [ ] **Step 1: 디렉터리와 가상환경 준비**

저장소 루트 `.gitignore`에 아래를 추가한다.

```gitignore
backend/.venv/
backend/data/
__pycache__/
*.egg-info/
.pytest_cache/
```

`backend/pyproject.toml`:

```toml
[project]
name = "coding-test-web"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlmodel>=0.0.48",
  "itsdangerous>=2.2",
  "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]

[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

빈 파일 `backend/app/__init__.py`, `backend/tests/__init__.py`를 만든 뒤:

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(admin_password="pw", secret_key="test-secret", data_dir=tmp_path / "data")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
```

`backend/tests/test_health.py`:

```python
from pathlib import Path

import pytest

from app.config import load_settings


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_load_settings_requires_env(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        load_settings()


def test_load_settings_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_PASSWORD", "a")
    monkeypatch.setenv("SECRET_KEY", "b")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COOKIE_SECURE", "1")
    s = load_settings()
    assert (s.admin_password, s.secret_key, s.data_dir, s.cookie_secure) == ("a", "b", Path(tmp_path), True)
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `pytest tests/test_health.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 4: 구현**

`backend/app/config.py`:

```python
"""환경변수에서 읽는 설정."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    admin_password: str
    secret_key: str
    data_dir: Path
    cookie_secure: bool = False

    @property
    def db_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"


def load_settings() -> Settings:
    password = os.environ.get("ADMIN_PASSWORD")
    secret = os.environ.get("SECRET_KEY")
    if not password or not secret:
        raise RuntimeError("ADMIN_PASSWORD와 SECRET_KEY 환경변수가 필요합니다.")
    return Settings(
        admin_password=password,
        secret_key=secret,
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        cookie_secure=os.environ.get("COOKIE_SECURE", "0") == "1",
    )
```

`backend/app/main.py`:

```python
"""FastAPI 앱 생성. 실행: uvicorn app.main:create_app --factory --workers 1"""
from fastapi import FastAPI

from app.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    app = FastAPI(title="coding-test-web")
    app.state.settings = settings

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `pytest tests/test_health.py -q` 다음 `pytest -q`
Expected: 전체 `3 passed`

- [ ] **Step 6: 커밋**

```bash
git add .gitignore backend/pyproject.toml backend/app/__init__.py backend/app/config.py backend/app/main.py backend/tests/__init__.py backend/tests/conftest.py backend/tests/test_health.py
git commit -m "feat(backend): 앱 팩토리와 설정"
```

---

### Task 2: 그래프 구조와 저장 전 검사 (순수 함수)

시험장 JSON을 파싱하고 회차를 열 수 있는지 검사한다. DB와 무관하다.

**Files:**
- Create: `backend/app/engine/__init__.py`
- Create: `backend/app/engine/graph.py`
- Create: `backend/tests/graphs.py`
- Test: `backend/tests/test_graph.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `app.engine.graph`: `Graph(boxes: dict[str, Box], edges: tuple[Edge, ...])`, 메서드 `incoming(box_id)`, `outgoing(box_id)`, `edge(edge_id)`, `start_boxes()`, `ancestors(box_id) -> set[str]`
  - `Box(id, type, title, markdown, attachments_enabled, files: tuple[EditorFile, ...])`, `EditorFile(name, starter)`, `Edge(id, source, target, mode)`, `Issue(message, box_ids)`
  - `parse_graph(data: dict) -> Graph` (모양이 잘못되면 `GraphError`), `validate_graph(graph) -> list[Issue]`
  - 상수 `BOX_TYPES`, `EDGE_MODES`, `MAX_PERSONAL_BOXES = 6`
  - 테스트 도우미 `tests/graphs.py`: `box(...)`, `parking_graph_dict()`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/graphs.py`:

```python
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
```

`backend/tests/test_graph.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_graph.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.engine'`

- [ ] **Step 3: 구현**

빈 파일 `backend/app/engine/__init__.py`를 만든다.

`backend/app/engine/graph.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_graph.py -q` 다음 `pytest -q`
Expected: 전체 `19 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/app/engine/__init__.py backend/app/engine/graph.py backend/tests/graphs.py backend/tests/test_graph.py
git commit -m "feat(engine): 그래프 파싱과 저장 전 검사"
```

---

### Task 3: 박스 열림 규칙 엔진 (순수 함수)

설계 3장 '박스 열림 규칙'을 그대로 구현한다. 회차 진행의 핵심이라 경계 사례까지 테스트한다.

**Files:**
- Create: `backend/app/engine/flow.py`
- Test: `backend/tests/test_flow.py`

**Interfaces:**
- Consumes: Task 2의 `Graph`, `Edge`, `parse_graph`
- Produces:
  - `app.engine.flow`: 상수 `LOCKED`, `OPEN`, `CLOSED`
  - `FlowState(states: dict[str, str], submitted: frozenset, final_team: frozenset, approved: frozenset)`
  - `Transition(opened: tuple, closed: tuple, finished: bool)`, 속성 `changed`
  - `advance(graph, fs) -> Transition`, `can_approve(edge, states) -> bool`, `seed_team_files(graph, team_id, submissions) -> dict[str, str]`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_flow.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_flow.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.engine.flow'`

- [ ] **Step 3: 구현**

`backend/app/engine/flow.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_flow.py -q` 다음 `pytest -q`
Expected: 전체 `28 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/app/engine/flow.py backend/tests/test_flow.py
git commit -m "feat(engine): 박스 열림 규칙"
```

---

### Task 4: DB 테이블과 웹소켓 허브

설계 4장의 테이블을 SQLModel로 만들고, 실시간 알림을 보낼 허브를 둔다. 허브는 소켓 객체만 알면 되므로 가짜 소켓으로 테스트한다.

> 참고: 시각은 timezone이 붙은 UTC로 다룬다. SQLModel 0.0.48부터 naive datetime 저장을 거부하기 때문이다(`ValueError: Datetime values must have timezone information`).

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/app/db.py`
- Create: `backend/app/ws/__init__.py`
- Create: `backend/app/ws/hub.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_models_hub.py`

**Interfaces:**
- Consumes: Task 1의 `Settings`, `create_app`
- Produces:
  - `app.models`: `Template`, `TemplateFile`, `Run`, `RunFile`, `Participant`, `BoxState`, `EdgeApproval`, `Submission`, `TeamDraft`, `TeamVersion`, 함수 `utcnow()`, `iso(dt) -> str | None`, `empty_graph()`
  - `app.db.make_engine(settings) -> Engine`, `init_db(engine)`
  - `app.ws.hub.Hub`: `connect(run_id, conn)`, `disconnect(run_id, conn)`, `online(run_id) -> set[int]`, `async to_all/to_admins(run_id, event, data)`, `async to_participants(run_id, event, data, exclude=None)`, `async kick(run_id, participant_id, keep_token_hash=None)`
  - `app.ws.hub.Conn(socket, role, participant_id=None, token_hash=None)`
  - `app.state.engine`, `app.state.hub`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_models_hub.py`:

```python
import asyncio

from sqlalchemy import inspect
from sqlmodel import Session

from app.models import Template
from app.ws.hub import Conn, Hub


def test_tables_created(app):
    names = set(inspect(app.state.engine).get_table_names())
    assert {
        "templates", "template_files", "runs", "run_files", "participants",
        "box_states", "edge_approvals", "submissions", "team_drafts", "team_versions",
    } <= names


def test_json_column_roundtrip(app):
    with Session(app.state.engine) as session:
        t = Template(name="t", graph={"boxes": [{"id": "x"}], "edges": []})
        session.add(t)
        session.commit()
        session.refresh(t)
        assert t.graph["boxes"][0]["id"] == "x"


class FakeSocket:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self.closed_with: int | None = None
        self.fail = fail

    async def send_json(self, data) -> None:
        if self.fail:
            raise RuntimeError("gone")
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


def test_hub_routes_messages_by_role():
    hub = Hub()
    admin, p1, p2 = FakeSocket(), FakeSocket(), FakeSocket()
    hub.connect(1, Conn(admin, "admin"))
    hub.connect(1, Conn(p1, "participant", participant_id=10))
    hub.connect(1, Conn(p2, "participant", participant_id=11))

    async def scenario():
        await hub.to_admins(1, "a", {})
        await hub.to_participants(1, "p", {}, exclude=10)
        await hub.to_all(1, "all", {"x": 1})

    asyncio.run(scenario())
    assert [m["event"] for m in admin.sent] == ["a", "all"]
    assert [m["event"] for m in p1.sent] == ["all"]
    assert [m["event"] for m in p2.sent] == ["p", "all"]
    assert hub.online(1) == {10, 11}


def test_hub_drops_broken_socket_and_kicks():
    hub = Hub()
    broken, old, new = FakeSocket(fail=True), FakeSocket(), FakeSocket()
    hub.connect(1, Conn(broken, "participant", participant_id=1))
    hub.connect(1, Conn(old, "participant", participant_id=2, token_hash="old"))
    hub.connect(1, Conn(new, "participant", participant_id=2, token_hash="new"))

    async def scenario():
        await hub.to_all(1, "x", {})
        await hub.kick(1, 2, keep_token_hash="new")

    asyncio.run(scenario())
    assert hub.online(1) == {2}
    assert old.closed_with == 4401
    assert new.closed_with is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_models_hub.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: 구현**

`backend/app/models.py`:

```python
"""DB 테이블. 시각은 모두 timezone이 붙은 UTC(datetime)로 다룬다. SQLModel 0.0.48+는 naive datetime 저장을 거부한다."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def empty_graph() -> dict:
    return {"boxes": [], "edges": []}


class Template(SQLModel, table=True):
    __tablename__ = "templates"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    graph: dict = Field(default_factory=empty_graph, sa_column=Column(JSON, nullable=False))
    valid: bool = False
    updated_at: datetime = Field(default_factory=utcnow)


class TemplateFile(SQLModel, table=True):
    __tablename__ = "template_files"
    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="templates.id", index=True)
    box_id: str
    filename: str
    stored_path: str
    size: int


class Run(SQLModel, table=True):
    __tablename__ = "runs"
    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="templates.id", index=True)
    name: str
    graph_snapshot: dict = Field(default_factory=empty_graph, sa_column=Column(JSON, nullable=False))
    entry_code: str = Field(index=True, unique=True)
    status: str = "lobby"  # lobby / running / finished
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunFile(SQLModel, table=True):
    __tablename__ = "run_files"
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    filename: str
    stored_path: str
    size: int


class Participant(SQLModel, table=True):
    __tablename__ = "participants"
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    name: str
    token_hash: str = Field(index=True)
    rejoin_token_hash: str | None = Field(default=None, index=True)
    assigned_box_id: str | None = None
    is_leader: bool = False
    joined_at: datetime = Field(default_factory=utcnow)
    last_active_at: datetime | None = None


class BoxState(SQLModel, table=True):
    __tablename__ = "box_states"
    __table_args__ = (UniqueConstraint("run_id", "box_id"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    state: str = "locked"  # locked / open / closed
    opened_at: datetime | None = None
    closed_at: datetime | None = None


class EdgeApproval(SQLModel, table=True):
    __tablename__ = "edge_approvals"
    __table_args__ = (UniqueConstraint("run_id", "edge_id"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    edge_id: str
    approved_at: datetime = Field(default_factory=utcnow)


class Submission(SQLModel, table=True):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("run_id", "box_id"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    participant_id: int = Field(foreign_key="participants.id")
    files: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    submitted_at: datetime = Field(default_factory=utcnow)


class TeamDraft(SQLModel, table=True):
    __tablename__ = "team_drafts"
    __table_args__ = (UniqueConstraint("run_id", "box_id"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    files: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    updated_at: datetime = Field(default_factory=utcnow)


class TeamVersion(SQLModel, table=True):
    __tablename__ = "team_versions"
    __table_args__ = (UniqueConstraint("run_id", "box_id", "version_no"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    version_no: int
    files: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    saved_at: datetime = Field(default_factory=utcnow)
    is_final: bool = False
```

`backend/app/db.py`:

```python
"""DB 엔진 생성과 테이블 준비."""
from sqlalchemy import Engine, event
from sqlmodel import SQLModel, create_engine

from app import models  # noqa: F401  (테이블을 metadata에 등록)
from app.config import Settings


def make_engine(settings: Settings) -> Engine:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
```

빈 파일 `backend/app/ws/__init__.py`를 만든다.

`backend/app/ws/hub.py`:

```python
"""회차별 웹소켓 연결을 들고 이벤트를 보낸다. uvicorn 워커 1개를 전제로 메모리에 둔다."""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol


class Socket(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


@dataclass(eq=False)
class Conn:
    socket: Socket
    role: str                       # "admin" | "participant"
    participant_id: int | None = None
    token_hash: str | None = None


class Hub:
    def __init__(self) -> None:
        self._conns: dict[int, list[Conn]] = defaultdict(list)

    def connect(self, run_id: int, conn: Conn) -> None:
        self._conns[run_id].append(conn)

    def disconnect(self, run_id: int, conn: Conn) -> None:
        conns = self._conns.get(run_id, [])
        if conn in conns:
            conns.remove(conn)

    def online(self, run_id: int) -> set[int]:
        return {
            c.participant_id
            for c in self._conns.get(run_id, [])
            if c.role == "participant" and c.participant_id is not None
        }

    async def _send(self, run_id: int, targets: list[Conn], event: str, data: dict) -> None:
        message = {"event": event, "data": data}
        for conn in targets:
            try:
                await conn.socket.send_json(message)
            except Exception:
                self.disconnect(run_id, conn)

    async def to_all(self, run_id: int, event: str, data: dict) -> None:
        await self._send(run_id, list(self._conns.get(run_id, [])), event, data)

    async def to_admins(self, run_id: int, event: str, data: dict) -> None:
        targets = [c for c in self._conns.get(run_id, []) if c.role == "admin"]
        await self._send(run_id, targets, event, data)

    async def to_participants(
        self, run_id: int, event: str, data: dict, exclude: int | None = None
    ) -> None:
        targets = [
            c for c in self._conns.get(run_id, [])
            if c.role == "participant" and c.participant_id != exclude
        ]
        await self._send(run_id, targets, event, data)

    async def kick(self, run_id: int, participant_id: int, keep_token_hash: str | None = None) -> None:
        """해당 참가자의 연결 중 keep_token_hash가 아닌 것을 끊는다(재입장 승인 시 이전 기기)."""
        targets = [
            c for c in self._conns.get(run_id, [])
            if c.participant_id == participant_id and c.token_hash != keep_token_hash
        ]
        for conn in targets:
            self.disconnect(run_id, conn)
            try:
                await conn.socket.close(code=4401)
            except Exception:
                pass
```

`backend/app/main.py` 변경:

```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -3,11 +3,17 @@
 
 from app.config import Settings, load_settings
+from app.db import init_db, make_engine
+from app.ws.hub import Hub
 
 
 def create_app(settings: Settings | None = None) -> FastAPI:
     settings = settings or load_settings()
+    engine = make_engine(settings)
+    init_db(engine)
 
     app = FastAPI(title="coding-test-web")
     app.state.settings = settings
+    app.state.engine = engine
+    app.state.hub = Hub()
 
     @app.get("/api/health")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_models_hub.py -q` 다음 `pytest -q`
Expected: 전체 `32 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/app/models.py backend/app/db.py backend/app/ws/__init__.py backend/app/ws/hub.py backend/tests/test_models_hub.py backend/app/main.py
git commit -m "feat(backend): DB 테이블과 웹소켓 허브"
```

---

### Task 5: 관리자 로그인과 공용 의존성

관리자는 비밀번호 하나로 로그인하고 서명 쿠키로 세션을 유지한다. 참가자 토큰 인증 의존성도 여기서 만든다(사용은 Task 8부터).

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/app/deps.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/admin.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_admin_auth.py`

**Interfaces:**
- Consumes: Task 4의 `Participant`, `Hub`
- Produces:
  - `app.auth`: `ADMIN_COOKIE`, `ADMIN_MAX_AGE`, `password_ok`, `make_admin_cookie`, `check_admin_cookie(settings, value) -> bool`, `new_token() -> str`, `hash_token(token) -> str`
  - `app.deps`: `SessionDep`, `SettingsDep`, `HubDep`, `require_admin`, `ParticipantDep`(헤더 `X-Participant-Token`; 재입장 대기 토큰이면 409), `TOKEN_HEADER`
  - API: `POST /api/admin/login {password}`, `POST /api/admin/logout`, `GET /api/admin/me`
  - pytest 픽스처 `admin_client`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_admin_auth.py`:

```python
from app.auth import check_admin_cookie, hash_token, make_admin_cookie, new_token
from app.config import Settings


def test_cookie_signed_with_secret(tmp_path):
    a = Settings("pw", "secret-a", tmp_path)
    b = Settings("pw", "secret-b", tmp_path)
    cookie = make_admin_cookie(a)
    assert check_admin_cookie(a, cookie)
    assert not check_admin_cookie(b, cookie)
    assert not check_admin_cookie(a, None)
    assert not check_admin_cookie(a, "garbage")


def test_token_hash_is_stable_and_tokens_unique():
    t1, t2 = new_token(), new_token()
    assert t1 != t2
    assert hash_token(t1) == hash_token(t1)
    assert len(hash_token(t1)) == 64


def test_login_wrong_password(client):
    r = client.post("/api/admin/login", json={"password": "nope"})
    assert r.status_code == 401
    assert client.get("/api/admin/me").status_code == 401


def test_login_logout(client):
    assert client.post("/api/admin/login", json={"password": "pw"}).status_code == 200
    assert client.get("/api/admin/me").json() == {"admin": True}
    client.post("/api/admin/logout")
    assert client.get("/api/admin/me").status_code == 401
```

`backend/tests/conftest.py` 변경:

```diff
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -21,2 +21,8 @@
         yield c
 
+
+@pytest.fixture
+def admin_client(client):
+    r = client.post("/api/admin/login", json={"password": "pw"})
+    assert r.status_code == 200, r.text
+    return client
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_admin_auth.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: 구현**

`backend/app/auth.py`:

```python
"""관리자 세션 쿠키와 참가자 토큰."""
import hashlib
import hmac
import secrets

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import Settings

ADMIN_COOKIE = "admin_session"
ADMIN_MAX_AGE = 12 * 60 * 60


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="admin-session")


def password_ok(settings: Settings, password: str) -> bool:
    return hmac.compare_digest(password.encode("utf-8"), settings.admin_password.encode("utf-8"))


def make_admin_cookie(settings: Settings) -> str:
    return _serializer(settings).dumps({"admin": True})


def check_admin_cookie(settings: Settings, value: str | None) -> bool:
    if not value:
        return False
    try:
        data = _serializer(settings).loads(value, max_age=ADMIN_MAX_AGE)
    except BadSignature:
        return False
    return isinstance(data, dict) and data.get("admin") is True


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
```

`backend/app/deps.py`:

```python
"""FastAPI 의존성: DB 세션, 설정, 허브, 관리자/참가자 인증."""
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from app.auth import ADMIN_COOKIE, check_admin_cookie, hash_token
from app.config import Settings
from app.models import Participant
from app.ws.hub import Hub

TOKEN_HEADER = "X-Participant-Token"


def get_session(request: Request):
    with Session(request.app.state.engine) as session:
        yield session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_hub(request: Request) -> Hub:
    return request.app.state.hub


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
HubDep = Annotated[Hub, Depends(get_hub)]


def require_admin(request: Request) -> None:
    if not check_admin_cookie(request.app.state.settings, request.cookies.get(ADMIN_COOKIE)):
        raise HTTPException(401, "관리자 로그인이 필요합니다.")


def get_participant(request: Request, session: SessionDep) -> Participant:
    token = request.headers.get(TOKEN_HEADER)
    if not token:
        raise HTTPException(401, "입장 정보가 없습니다.")
    hashed = hash_token(token)
    participant = session.exec(
        select(Participant).where(Participant.token_hash == hashed)
    ).first()
    if participant is not None:
        return participant
    pending = session.exec(
        select(Participant).where(Participant.rejoin_token_hash == hashed)
    ).first()
    if pending is not None:
        raise HTTPException(409, "재입장 승인을 기다리는 중입니다.")
    raise HTTPException(401, "입장 정보가 올바르지 않습니다.")


ParticipantDep = Annotated[Participant, Depends(get_participant)]
```

빈 파일 `backend/app/api/__init__.py`를 만든다.

`backend/app/api/admin.py`:

```python
"""관리자 로그인 API."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.auth import ADMIN_COOKIE, ADMIN_MAX_AGE, make_admin_cookie, password_ok
from app.deps import SettingsDep, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response, settings: SettingsDep) -> dict:
    if not password_ok(settings, body.password):
        raise HTTPException(401, "비밀번호가 올바르지 않습니다.")
    response.set_cookie(
        ADMIN_COOKIE,
        make_admin_cookie(settings),
        max_age=ADMIN_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(ADMIN_COOKIE)
    return {"ok": True}


@router.get("/me", dependencies=[Depends(require_admin)])
def me() -> dict:
    return {"admin": True}
```

`backend/app/main.py` 변경:

```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -2,4 +2,5 @@
 from fastapi import FastAPI
 
+from app.api import admin
 from app.config import Settings, load_settings
 from app.db import init_db, make_engine
@@ -17,4 +18,7 @@
     app.state.hub = Hub()
 
+    for module in (admin,):
+        app.include_router(module.router)
+
     @app.get("/api/health")
     def health() -> dict:
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_admin_auth.py -q` 다음 `pytest -q`
Expected: 전체 `36 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/app/auth.py backend/app/deps.py backend/app/api/__init__.py backend/app/api/admin.py backend/tests/test_admin_auth.py backend/app/main.py backend/tests/conftest.py
git commit -m "feat(api): 관리자 로그인과 공용 의존성"
```

---

### Task 6: 시험장(템플릿) API와 첨부 파일

시험장을 만들고 고치고 복제한다. 저장은 항상 되고, 검사 결과(`valid`, `issues`)를 함께 돌려준다. 문제 박스 강조를 위해 issue마다 `box_ids`가 있다.

> 참고: 회차가 있는 시험장은 삭제할 수 없다(409, Task 7에서 테스트). 설계 문서는 '저장 시 검사 실패하면 강조'라고 했는데, 작업 중인 시험장을 잃지 않도록 저장은 허용하고 `valid=false`면 회차를 못 열게 했다.

**Files:**
- Create: `backend/app/storage.py`
- Create: `backend/app/api/templates.py`
- Create: `backend/tests/helpers.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_templates.py`

**Interfaces:**
- Consumes: Task 2의 `parse_graph`, `validate_graph`; Task 5의 `require_admin`, `SessionDep`, `SettingsDep`
- Produces:
  - `app.storage`: `save_upload(files_dir, subdir, upload) -> (rel, size)`(10MB 초과 413), `copy_stored`, `delete_stored`, `stored_path`, `safe_name`
  - API: `GET/POST /api/templates`, `GET/PUT/DELETE /api/templates/{id}`, `POST /api/templates/{id}/duplicate`, `GET/POST /api/templates/{id}/files`, `GET/DELETE /api/templates/{id}/files/{file_id}`
  - 응답 `template_out`: `{id, name, description, graph, valid, issues: [{message, box_ids}], updated_at}`
  - 테스트 도우미 `tests/helpers.py` 전체(뒤 작업에서 쓰는 함수 포함)

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/helpers.py`:

```python
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
```

`backend/tests/test_templates.py`:

```python
from tests.graphs import parking_graph_dict
from tests.helpers import create_template


def test_requires_admin(client):
    assert client.get("/api/templates").status_code == 401


def test_create_valid_template(admin_client):
    t = create_template(admin_client)
    assert t["valid"] is True
    assert t["issues"] == []
    assert [x["name"] for x in admin_client.get("/api/templates").json()] == ["주차장"]


def test_empty_template_is_saved_but_invalid(admin_client):
    r = admin_client.post("/api/templates", json={"name": "빈 시험장"})
    assert r.status_code == 201
    body = r.json()
    assert body["valid"] is False
    assert body["issues"] == [{"message": "박스가 하나도 없습니다.", "box_ids": []}]


def test_update_reports_issues_with_box_ids(admin_client):
    t = create_template(admin_client)
    graph = parking_graph_dict()
    graph["boxes"].append({"id": "x", "type": "common", "title": "x", "config": {}})
    r = admin_client.put(f"/api/templates/{t['id']}", json={"name": "주차장 v2", "graph": graph})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "주차장 v2"
    assert body["valid"] is False
    assert body["issues"] == [{"message": "결과 박스까지 이어지지 않는 박스가 있습니다.", "box_ids": ["x"]}]


def test_malformed_graph_is_an_issue_not_a_crash(admin_client):
    r = admin_client.post("/api/templates", json={"name": "깨짐", "graph": {"boxes": [{"id": "x"}]}})
    assert r.status_code == 201
    assert r.json()["issues"] == [{"message": "박스에 id와 type이 필요합니다.", "box_ids": []}]


def test_duplicate_and_delete(admin_client):
    t = create_template(admin_client)
    admin_client.post(f"/api/templates/{t['id']}/files", data={"box_id": "story"}, files={"file": ("안내.txt", b"hello")})
    clone = admin_client.post(f"/api/templates/{t['id']}/duplicate").json()
    assert clone["name"] == "주차장 사본"
    assert clone["valid"] is True
    clone_files = admin_client.get(f"/api/templates/{clone['id']}/files").json()
    assert [f["filename"] for f in clone_files] == ["안내.txt"]
    assert admin_client.delete(f"/api/templates/{t['id']}").status_code == 204
    assert admin_client.get(f"/api/templates/{t['id']}").status_code == 404
    r = admin_client.get(f"/api/templates/{clone['id']}/files/{clone_files[0]['id']}")
    assert r.content == b"hello"


def test_upload_download_delete_file(admin_client):
    t = create_template(admin_client)
    r = admin_client.post(
        f"/api/templates/{t['id']}/files", data={"box_id": "a"}, files={"file": ("../../evil name.py", b"x = 1\n")}
    )
    assert r.status_code == 201
    f = r.json()
    assert f["filename"] == "evil name.py"
    assert f["size"] == 6
    got = admin_client.get(f"/api/templates/{t['id']}/files/{f['id']}")
    assert got.content == b"x = 1\n"
    assert admin_client.delete(f"/api/templates/{t['id']}/files/{f['id']}").status_code == 204
    assert admin_client.get(f"/api/templates/{t['id']}/files").json() == []


def test_upload_too_large(admin_client):
    t = create_template(admin_client)
    big = b"0" * (10 * 1024 * 1024 + 1)
    r = admin_client.post(f"/api/templates/{t['id']}/files", data={"box_id": "a"}, files={"file": ("big.bin", big)})
    assert r.status_code == 413
    assert admin_client.get(f"/api/templates/{t['id']}/files").json() == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_templates.py -q`
Expected: FAIL — `404 Not Found`(라우터 없음)

- [ ] **Step 3: 구현**

`backend/app/storage.py`:

```python
"""첨부 파일 저장. DB에는 files_dir 기준 상대 경로를 둔다."""
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


def safe_name(name: str | None) -> str:
    base = Path(name or "").name.strip() or "file"
    return base[:120]


def stored_path(files_dir: Path, rel: str) -> Path:
    return files_dir / rel


async def save_upload(
    files_dir: Path, subdir: str, upload: UploadFile, max_bytes: int = MAX_ATTACHMENT_BYTES
) -> tuple[str, int]:
    rel = Path(subdir) / f"{uuid.uuid4().hex}_{safe_name(upload.filename)}"
    target = files_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    too_big = False
    with target.open("wb") as out:
        while chunk := await upload.read(CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                too_big = True
                break
            out.write(chunk)
    if too_big:
        target.unlink(missing_ok=True)
        raise HTTPException(413, "첨부 파일은 10MB까지 올릴 수 있습니다.")
    return rel.as_posix(), size


def copy_stored(files_dir: Path, rel: str, subdir: str) -> str:
    source = files_dir / rel
    original = source.name.split("_", 1)[-1]
    new_rel = Path(subdir) / f"{uuid.uuid4().hex}_{original}"
    (files_dir / new_rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, files_dir / new_rel)
    return new_rel.as_posix()


def delete_stored(files_dir: Path, rel: str) -> None:
    (files_dir / rel).unlink(missing_ok=True)
```

`backend/app/api/templates.py`:

```python
"""시험장(템플릿) 관리 API. 관리자 전용."""
import copy

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.deps import SessionDep, SettingsDep, require_admin
from app.engine.graph import GraphError, Issue, parse_graph, validate_graph
from app.models import Run, Template, TemplateFile, empty_graph, iso, utcnow
from app.storage import copy_stored, delete_stored, safe_name, save_upload, stored_path

router = APIRouter(
    prefix="/api/templates", tags=["templates"], dependencies=[Depends(require_admin)]
)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    graph: dict = Field(default_factory=empty_graph)


def check_graph(data: dict) -> list[Issue]:
    try:
        graph = parse_graph(data)
    except GraphError as exc:
        return [Issue(str(exc))]
    return validate_graph(graph)


def template_out(t: Template) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "graph": t.graph,
        "valid": t.valid,
        "issues": [{"message": i.message, "box_ids": list(i.box_ids)} for i in check_graph(t.graph)],
        "updated_at": iso(t.updated_at),
    }


def file_out(f: TemplateFile) -> dict:
    return {"id": f.id, "box_id": f.box_id, "filename": f.filename, "size": f.size}


def get_template(session: Session, template_id: int) -> Template:
    template = session.get(Template, template_id)
    if template is None:
        raise HTTPException(404, "시험장을 찾을 수 없습니다.")
    return template


def template_files(session: Session, template_id: int) -> list[TemplateFile]:
    return list(
        session.exec(
            select(TemplateFile).where(TemplateFile.template_id == template_id).order_by(col(TemplateFile.id))
        ).all()
    )


@router.get("")
def list_templates(session: SessionDep) -> list[dict]:
    rows = session.exec(select(Template).order_by(col(Template.updated_at).desc())).all()
    return [
        {"id": t.id, "name": t.name, "description": t.description, "valid": t.valid, "updated_at": iso(t.updated_at)}
        for t in rows
    ]


@router.post("", status_code=201)
def create_template(body: TemplateIn, session: SessionDep) -> dict:
    template = Template(
        name=body.name,
        description=body.description,
        graph=body.graph,
        valid=not check_graph(body.graph),
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    return template_out(template)


@router.get("/{template_id}")
def read_template(template_id: int, session: SessionDep) -> dict:
    return template_out(get_template(session, template_id))


@router.put("/{template_id}")
def update_template(template_id: int, body: TemplateIn, session: SessionDep) -> dict:
    template = get_template(session, template_id)
    template.name = body.name
    template.description = body.description
    template.graph = body.graph
    template.valid = not check_graph(body.graph)
    template.updated_at = utcnow()
    session.add(template)
    session.commit()
    session.refresh(template)
    return template_out(template)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, session: SessionDep, settings: SettingsDep) -> Response:
    template = get_template(session, template_id)
    if session.exec(select(Run).where(Run.template_id == template.id)).first() is not None:
        raise HTTPException(409, "회차가 있는 시험장은 삭제할 수 없습니다. 복제해서 새로 만드세요.")
    for f in template_files(session, template.id):
        delete_stored(settings.files_dir, f.stored_path)
        session.delete(f)
    session.flush()
    session.delete(template)
    session.commit()
    return Response(status_code=204)


@router.post("/{template_id}/duplicate", status_code=201)
def duplicate_template(template_id: int, session: SessionDep, settings: SettingsDep) -> dict:
    source = get_template(session, template_id)
    clone = Template(
        name=f"{source.name} 사본",
        description=source.description,
        graph=copy.deepcopy(source.graph),
        valid=source.valid,
    )
    session.add(clone)
    session.flush()
    for f in template_files(session, source.id):
        session.add(
            TemplateFile(
                template_id=clone.id,
                box_id=f.box_id,
                filename=f.filename,
                stored_path=copy_stored(settings.files_dir, f.stored_path, f"templates/{clone.id}"),
                size=f.size,
            )
        )
    session.commit()
    session.refresh(clone)
    return template_out(clone)


@router.get("/{template_id}/files")
def list_files(template_id: int, session: SessionDep) -> list[dict]:
    get_template(session, template_id)
    return [file_out(f) for f in template_files(session, template_id)]


@router.post("/{template_id}/files", status_code=201)
async def upload_file(
    template_id: int,
    session: SessionDep,
    settings: SettingsDep,
    box_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    template = get_template(session, template_id)
    rel, size = await save_upload(settings.files_dir, f"templates/{template.id}", file)
    record = TemplateFile(
        template_id=template.id, box_id=box_id, filename=safe_name(file.filename), stored_path=rel, size=size
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return file_out(record)


def _template_file(session: Session, template_id: int, file_id: int) -> TemplateFile:
    record = session.get(TemplateFile, file_id)
    if record is None or record.template_id != template_id:
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    return record


@router.get("/{template_id}/files/{file_id}")
def download_file(template_id: int, file_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
    record = _template_file(session, template_id, file_id)
    return FileResponse(stored_path(settings.files_dir, record.stored_path), filename=record.filename)


@router.delete("/{template_id}/files/{file_id}", status_code=204)
def delete_file(template_id: int, file_id: int, session: SessionDep, settings: SettingsDep) -> Response:
    record = _template_file(session, template_id, file_id)
    delete_stored(settings.files_dir, record.stored_path)
    session.delete(record)
    session.commit()
    return Response(status_code=204)
```

`backend/app/main.py` 변경:

```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -2,5 +2,5 @@
 from fastapi import FastAPI
 
-from app.api import admin
+from app.api import admin, templates
 from app.config import Settings, load_settings
 from app.db import init_db, make_engine
@@ -18,5 +18,5 @@
     app.state.hub = Hub()
 
-    for module in (admin,):
+    for module in (admin, templates):
         app.include_router(module.router)
 
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_templates.py -q` 다음 `pytest -q`
Expected: 전체 `44 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/app/storage.py backend/app/api/templates.py backend/tests/helpers.py backend/tests/test_templates.py backend/app/main.py
git commit -m "feat(api): 시험장 API와 첨부 파일"
```

---

### Task 7: 회차 생성, 시작, 관리자 상태 화면

시험장을 복사(스냅샷)해 회차를 열고, 시작하면 엔진으로 박스를 연다. 관리자 진행 화면이 쓸 상태 묶음과 참가자 배정·재입장·문제 수정 API도 여기 둔다.

> 참고: 참가자 관련 엔드포인트(배정, 재입장)는 참가자가 입장할 수 있어야 테스트할 수 있어서 Task 8에서 검증한다.

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/runs.py`
- Create: `backend/app/services/views.py`
- Create: `backend/app/api/runs.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_runs.py`

**Interfaces:**
- Consumes: Task 3의 `advance`, `seed_team_files`; Task 4의 테이블과 `Hub`; Task 6의 `copy_stored`
- Produces:
  - `app.services.runs`: `new_entry_code`, `get_run`, `require_running`, `graph_of`, `state_rows`, `submissions_by_box`, `latest_final`, `flow_state`, `version_summary`, `draft_out`, `apply_transition`, `async advance_run(session, hub, run) -> Transition`
  - `app.services.views`: `run_summary`, `participant_out(p, online)`, `files_by_box`, `admin_state(session, run, online)`, `can_see_box`, `participant_state(session, run, me)`
  - API(관리자): `POST /api/templates/{id}/runs`, `GET /api/runs`, `GET /api/runs/{id}/state`, `POST /api/runs/{id}/start`, `POST /api/runs/{id}/finish`, `PATCH /api/runs/{id}/participants/{pid}`, `POST .../approve-rejoin`, `DELETE .../participants/{pid}`, `PATCH /api/runs/{id}/boxes/{box_id}`, `GET .../boxes/{box_id}/submission`, `GET .../boxes/{box_id}/versions`, `GET /api/runs/{id}/versions/{vid}`, `GET /api/runs/{id}/files/{fid}`
  - 웹소켓 이벤트 이름: `box_state_changed`, `run_status_changed`, `participant_updated`, `participant_removed`, `box_content_updated`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_runs.py`:

```python
from tests.helpers import create_template, open_run


def test_cannot_open_run_from_invalid_template(admin_client):
    t = admin_client.post("/api/templates", json={"name": "빈"}).json()
    r = admin_client.post(f"/api/templates/{t['id']}/runs", json={"name": "1기"})
    assert r.status_code == 409


def test_open_run_snapshot_and_lobby(admin_client):
    run = open_run(admin_client)
    assert run["status"] == "lobby"
    assert len(run["entry_code"]) == 6
    state = admin_client.get(f"/api/runs/{run['id']}/state").json()
    assert set(state["boxes"]) == {"story", "a", "b", "c", "d", "team", "result"}
    assert all(b["state"] == "locked" for b in state["boxes"].values())
    assert state["participants"] == []
    assert [r["id"] for r in admin_client.get("/api/runs").json()] == [run["id"]]


def test_template_edit_does_not_change_run(admin_client):
    t = create_template(admin_client)
    run = open_run(admin_client, t["id"])
    admin_client.put(f"/api/templates/{t['id']}", json={"name": "바뀜", "graph": {"boxes": [], "edges": []}})
    state = admin_client.get(f"/api/runs/{run['id']}/state").json()
    assert len(state["graph"]["boxes"]) == 7


def test_start_opens_personal_boxes(admin_client):
    run = open_run(admin_client)
    r = admin_client.post(f"/api/runs/{run['id']}/start")
    assert r.status_code == 200
    boxes = r.json()["boxes"]
    assert boxes["story"]["state"] == "closed"
    assert [boxes[x]["state"] for x in "abcd"] == ["open"] * 4
    assert boxes["team"]["state"] == "locked"
    assert admin_client.post(f"/api/runs/{run['id']}/start").status_code == 409


def test_template_with_run_cannot_be_deleted(admin_client):
    t = create_template(admin_client)
    open_run(admin_client, t["id"])
    assert admin_client.delete(f"/api/templates/{t['id']}").status_code == 409


def test_attachments_copied_into_run(admin_client):
    t = create_template(admin_client)
    admin_client.post(f"/api/templates/{t['id']}/files", data={"box_id": "story"}, files={"file": ("안내.txt", b"hi")})
    run = open_run(admin_client, t["id"])
    files = admin_client.get(f"/api/runs/{run['id']}/state").json()["files"]
    assert [f["filename"] for f in files["story"]] == ["안내.txt"]
    got = admin_client.get(f"/api/runs/{run['id']}/files/{files['story'][0]['id']}")
    assert got.content == b"hi"


def test_finish_run(admin_client):
    run = open_run(admin_client)
    assert admin_client.post(f"/api/runs/{run['id']}/finish").json()["run"]["status"] == "finished"
    assert admin_client.post(f"/api/runs/{run['id']}/finish").status_code == 409
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_runs.py -q`
Expected: FAIL — `404 Not Found`

- [ ] **Step 3: 구현**

빈 파일 `backend/app/services/__init__.py`를 만든다.

`backend/app/services/runs.py`:

```python
"""회차 진행 로직. REST API와 웹소켓이 함께 쓴다."""
import secrets

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.engine.flow import (
    CLOSED,
    OPEN,
    FlowState,
    Transition,
    advance,
    seed_team_files,
)
from app.engine.graph import Graph, parse_graph
from app.models import (
    BoxState,
    EdgeApproval,
    Run,
    Submission,
    TeamDraft,
    TeamVersion,
    iso,
    utcnow,
)
from app.ws.hub import Hub

ENTRY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_entry_code(session: Session) -> str:
    while True:
        code = "".join(secrets.choice(ENTRY_ALPHABET) for _ in range(6))
        if session.exec(select(Run).where(Run.entry_code == code)).first() is None:
            return code


def get_run(session: Session, run_id: int) -> Run:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "회차를 찾을 수 없습니다.")
    return run


def require_running(run: Run) -> None:
    if run.status != "running":
        raise HTTPException(409, "진행 중인 회차가 아닙니다.")


def graph_of(run: Run) -> Graph:
    return parse_graph(run.graph_snapshot)


def state_rows(session: Session, run_id: int) -> dict[str, BoxState]:
    rows = session.exec(select(BoxState).where(BoxState.run_id == run_id)).all()
    return {r.box_id: r for r in rows}


def submissions_by_box(session: Session, run_id: int) -> dict[str, dict[str, str]]:
    rows = session.exec(select(Submission).where(Submission.run_id == run_id)).all()
    return {s.box_id: dict(s.files) for s in rows}


def latest_final(session: Session, run_id: int, box_id: str) -> TeamVersion | None:
    return session.exec(
        select(TeamVersion)
        .where(TeamVersion.run_id == run_id, TeamVersion.box_id == box_id, TeamVersion.is_final)
        .order_by(col(TeamVersion.version_no).desc())
    ).first()


def flow_state(session: Session, run: Run) -> FlowState:
    rows = state_rows(session, run.id)
    final_rows = session.exec(
        select(TeamVersion).where(TeamVersion.run_id == run.id, TeamVersion.is_final)
    ).all()
    approvals = session.exec(select(EdgeApproval).where(EdgeApproval.run_id == run.id)).all()
    return FlowState(
        states={box_id: row.state for box_id, row in rows.items()},
        submitted=frozenset(submissions_by_box(session, run.id)),
        final_team=frozenset(v.box_id for v in final_rows),
        approved=frozenset(a.edge_id for a in approvals),
    )


def version_summary(version: TeamVersion) -> dict:
    return {
        "id": version.id,
        "box_id": version.box_id,
        "version_no": version.version_no,
        "saved_at": iso(version.saved_at),
        "is_final": version.is_final,
    }


def draft_out(draft: TeamDraft) -> dict:
    return {"box_id": draft.box_id, "files": draft.files, "updated_at": iso(draft.updated_at)}


def apply_transition(session: Session, run: Run, graph: Graph, tr: Transition) -> None:
    rows = state_rows(session, run.id)
    now = utcnow()
    for box_id in tr.opened:
        row = rows[box_id]
        row.state, row.opened_at = OPEN, now
        session.add(row)
        if graph.boxes[box_id].type == "team":
            files = seed_team_files(graph, box_id, submissions_by_box(session, run.id))
            session.add(TeamDraft(run_id=run.id, box_id=box_id, files=files, updated_at=now))
    for box_id in tr.closed:
        row = rows[box_id]
        row.state, row.closed_at = CLOSED, now
        session.add(row)
    if tr.finished and run.status != "finished":
        run.status, run.finished_at = "finished", now
        session.add(run)


async def advance_run(session: Session, hub: Hub, run: Run) -> Transition:
    """박스 열림 규칙을 적용하고 바뀐 박스를 모두에게 알린다."""
    graph = graph_of(run)
    tr = advance(graph, flow_state(session, run))
    if not tr.changed:
        return tr
    apply_transition(session, run, graph, tr)
    session.commit()
    rows = state_rows(session, run.id)
    for box_id in dict.fromkeys(tr.opened + tr.closed):
        await hub.to_all(run.id, "box_state_changed", {"box_id": box_id, "state": rows[box_id].state})
    if tr.finished:
        await hub.to_all(run.id, "run_status_changed", {"status": run.status})
    return tr
```

`backend/app/services/views.py`:

```python
"""API 응답용 상태 묶음. 참가자에게 보낼 내용은 여기서 권한에 맞게 거른다."""
from datetime import timedelta

from sqlmodel import Session, col, select

from app.engine.flow import LOCKED
from app.models import (
    EdgeApproval,
    Participant,
    Run,
    RunFile,
    Submission,
    TeamDraft,
    TeamVersion,
    iso,
    utcnow,
)
from app.services.runs import graph_of, latest_final, state_rows, version_summary

TYPING_WINDOW = timedelta(seconds=60)


def run_summary(run: Run) -> dict:
    return {
        "id": run.id,
        "template_id": run.template_id,
        "name": run.name,
        "entry_code": run.entry_code,
        "status": run.status,
        "created_at": iso(run.created_at),
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
    }


def participant_out(p: Participant, online: set[int]) -> dict:
    typing = p.last_active_at is not None and utcnow() - p.last_active_at < TYPING_WINDOW
    return {
        "id": p.id,
        "name": p.name,
        "assigned_box_id": p.assigned_box_id,
        "is_leader": p.is_leader,
        "online": p.id in online,
        "typing": typing,
        "last_active_at": iso(p.last_active_at),
        "rejoin_requested": p.rejoin_token_hash is not None,
    }


def files_by_box(session: Session, run_id: int) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in session.exec(select(RunFile).where(RunFile.run_id == run_id).order_by(col(RunFile.id))):
        out.setdefault(f.box_id, []).append({"id": f.id, "filename": f.filename, "size": f.size})
    return out


def admin_state(session: Session, run: Run, online: set[int]) -> dict:
    rows = state_rows(session, run.id)
    participants = session.exec(
        select(Participant).where(Participant.run_id == run.id).order_by(col(Participant.id))
    ).all()
    submissions = session.exec(select(Submission).where(Submission.run_id == run.id)).all()
    versions = session.exec(
        select(TeamVersion).where(TeamVersion.run_id == run.id).order_by(col(TeamVersion.version_no))
    ).all()
    approvals = session.exec(select(EdgeApproval).where(EdgeApproval.run_id == run.id)).all()
    team_versions: dict[str, list[dict]] = {}
    for v in versions:
        team_versions.setdefault(v.box_id, []).append(version_summary(v))
    return {
        "run": run_summary(run),
        "graph": run.graph_snapshot,
        "boxes": {
            box_id: {"state": r.state, "opened_at": iso(r.opened_at), "closed_at": iso(r.closed_at)}
            for box_id, r in rows.items()
        },
        "approved_edges": sorted(a.edge_id for a in approvals),
        "participants": [participant_out(p, online) for p in participants],
        "submissions": {
            s.box_id: {"participant_id": s.participant_id, "submitted_at": iso(s.submitted_at)}
            for s in submissions
        },
        "team_versions": team_versions,
        "files": files_by_box(session, run.id),
    }


def can_see_box(session: Session, run: Run, me: Participant, box_id: str) -> bool:
    box = graph_of(run).boxes.get(box_id)
    if box is None:
        return False
    if box.type == "personal" and box.id != me.assigned_box_id:
        return False
    row = state_rows(session, run.id).get(box_id)
    return row is not None and row.state != LOCKED


def participant_state(session: Session, run: Run, me: Participant) -> dict:
    graph = graph_of(run)
    rows = state_rows(session, run.id)
    attachments = files_by_box(session, run.id)

    boxes = []
    for box in graph.boxes.values():
        if box.type == "personal" and box.id != me.assigned_box_id:
            continue
        row = rows.get(box.id)
        state = row.state if row else LOCKED
        item: dict = {"id": box.id, "type": box.type, "title": box.title, "state": state}
        if state != LOCKED:
            item["markdown"] = box.markdown
            item["editor_files"] = [{"name": f.name, "starter": f.starter} for f in box.files]
            item["attachments"] = attachments.get(box.id, [])
        boxes.append(item)

    my_submission = None
    if me.assigned_box_id:
        sub = session.exec(
            select(Submission).where(
                Submission.run_id == run.id, Submission.box_id == me.assigned_box_id
            )
        ).first()
        if sub is not None:
            my_submission = {"box_id": sub.box_id, "files": sub.files, "submitted_at": iso(sub.submitted_at)}

    team: dict[str, dict] = {}
    team_ids = [b.id for b in graph.boxes.values() if b.type == "team"]
    for box_id in team_ids:
        row = rows.get(box_id)
        if row is None or row.state == LOCKED:
            continue
        draft = session.exec(
            select(TeamDraft).where(TeamDraft.run_id == run.id, TeamDraft.box_id == box_id)
        ).first()
        final = latest_final(session, run.id, box_id)
        team[box_id] = {
            "files": draft.files if draft else {},
            "updated_at": iso(draft.updated_at) if draft else None,
            "final": version_summary(final) if final else None,
        }

    result = None
    if run.status == "finished":
        result = {}
        for box_id in team_ids:
            final = latest_final(session, run.id, box_id)
            if final is not None:
                result[box_id] = final.files

    return {
        "run": {"id": run.id, "name": run.name, "status": run.status},
        "me": {
            "id": me.id,
            "name": me.name,
            "assigned_box_id": me.assigned_box_id,
            "is_leader": me.is_leader,
        },
        "boxes": boxes,
        "my_submission": my_submission,
        "team": team,
        "result": result,
    }
```

`backend/app/api/runs.py`:

```python
"""회차 관리 API. 관리자 전용."""
import copy

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.deps import HubDep, SessionDep, SettingsDep, require_admin
from app.engine.graph import parse_graph
from app.models import (
    BoxState,
    Participant,
    Run,
    RunFile,
    Submission,
    Template,
    TemplateFile,
    TeamVersion,
    iso,
    utcnow,
)
from app.services import runs as svc
from app.services.views import admin_state, participant_out, run_summary
from app.storage import copy_stored, stored_path
from app.ws.hub import Hub

router = APIRouter(prefix="/api", tags=["runs"], dependencies=[Depends(require_admin)])


class RunIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ParticipantPatch(BaseModel):
    assigned_box_id: str | None = None
    is_leader: bool | None = None


class BoxPatch(BaseModel):
    markdown: str = Field(max_length=100_000)


def _participant(session: Session, run: Run, participant_id: int) -> Participant:
    p = session.get(Participant, participant_id)
    if p is None or p.run_id != run.id:
        raise HTTPException(404, "참가자를 찾을 수 없습니다.")
    return p


async def _broadcast_participants(session: Session, hub: Hub, run: Run) -> None:
    online = hub.online(run.id)
    for p in session.exec(select(Participant).where(Participant.run_id == run.id)).all():
        await hub.to_all(run.id, "participant_updated", participant_out(p, online))


@router.post("/templates/{template_id}/runs", status_code=201)
def create_run(template_id: int, body: RunIn, session: SessionDep, settings: SettingsDep) -> dict:
    template = session.get(Template, template_id)
    if template is None:
        raise HTTPException(404, "시험장을 찾을 수 없습니다.")
    if not template.valid:
        raise HTTPException(409, "검사를 통과한 시험장만 회차를 열 수 있습니다.")
    graph = parse_graph(template.graph)
    run = Run(
        template_id=template.id,
        name=body.name,
        graph_snapshot=copy.deepcopy(template.graph),
        entry_code=svc.new_entry_code(session),
    )
    session.add(run)
    session.flush()
    for box_id in graph.boxes:
        session.add(BoxState(run_id=run.id, box_id=box_id))
    files = session.exec(select(TemplateFile).where(TemplateFile.template_id == template.id)).all()
    for f in files:
        session.add(
            RunFile(
                run_id=run.id,
                box_id=f.box_id,
                filename=f.filename,
                stored_path=copy_stored(settings.files_dir, f.stored_path, f"runs/{run.id}"),
                size=f.size,
            )
        )
    session.commit()
    session.refresh(run)
    return run_summary(run)


@router.get("/runs")
def list_runs(session: SessionDep, template_id: int | None = None) -> list[dict]:
    query = select(Run).order_by(col(Run.created_at).desc())
    if template_id is not None:
        query = query.where(Run.template_id == template_id)
    return [run_summary(r) for r in session.exec(query).all()]


@router.get("/runs/{run_id}/state")
def read_state(run_id: int, session: SessionDep, hub: HubDep) -> dict:
    run = svc.get_run(session, run_id)
    return admin_state(session, run, hub.online(run.id))


@router.post("/runs/{run_id}/start")
async def start_run(run_id: int, session: SessionDep, hub: HubDep) -> dict:
    run = svc.get_run(session, run_id)
    if run.status != "lobby":
        raise HTTPException(409, "이미 시작한 회차입니다.")
    run.status, run.started_at = "running", utcnow()
    session.add(run)
    session.commit()
    await hub.to_all(run.id, "run_status_changed", {"status": run.status})
    await svc.advance_run(session, hub, run)
    return admin_state(session, run, hub.online(run.id))


@router.post("/runs/{run_id}/finish")
async def finish_run(run_id: int, session: SessionDep, hub: HubDep) -> dict:
    run = svc.get_run(session, run_id)
    if run.status == "finished":
        raise HTTPException(409, "이미 종료된 회차입니다.")
    run.status, run.finished_at = "finished", utcnow()
    session.add(run)
    session.commit()
    await hub.to_all(run.id, "run_status_changed", {"status": run.status})
    return admin_state(session, run, hub.online(run.id))


@router.patch("/runs/{run_id}/participants/{participant_id}")
async def update_participant(
    run_id: int, participant_id: int, body: ParticipantPatch, session: SessionDep, hub: HubDep
) -> dict:
    run = svc.get_run(session, run_id)
    p = _participant(session, run, participant_id)
    if "assigned_box_id" in body.model_fields_set:
        box_id = body.assigned_box_id
        if box_id is not None:
            box = svc.graph_of(run).boxes.get(box_id)
            if box is None or box.type != "personal":
                raise HTTPException(422, "개인 박스에만 배정할 수 있습니다.")
            other = session.exec(
                select(Participant).where(
                    Participant.run_id == run.id,
                    Participant.assigned_box_id == box_id,
                    Participant.id != p.id,
                )
            ).first()
            if other is not None:
                raise HTTPException(409, f"{other.name}님이 이미 맡은 파트입니다.")
        p.assigned_box_id = box_id
    if body.is_leader is True:
        for other in session.exec(
            select(Participant).where(Participant.run_id == run.id, Participant.is_leader)
        ).all():
            other.is_leader = False
            session.add(other)
        p.is_leader = True
    elif body.is_leader is False:
        p.is_leader = False
    session.add(p)
    session.commit()
    await _broadcast_participants(session, hub, run)
    session.refresh(p)
    return participant_out(p, hub.online(run.id))


@router.post("/runs/{run_id}/participants/{participant_id}/approve-rejoin")
async def approve_rejoin(run_id: int, participant_id: int, session: SessionDep, hub: HubDep) -> dict:
    run = svc.get_run(session, run_id)
    p = _participant(session, run, participant_id)
    if p.rejoin_token_hash is None:
        raise HTTPException(409, "재입장 요청이 없습니다.")
    p.token_hash, p.rejoin_token_hash = p.rejoin_token_hash, None
    session.add(p)
    session.commit()
    session.refresh(p)
    await hub.kick(run.id, p.id, keep_token_hash=p.token_hash)
    await hub.to_admins(run.id, "participant_updated", participant_out(p, hub.online(run.id)))
    return participant_out(p, hub.online(run.id))


@router.delete("/runs/{run_id}/participants/{participant_id}", status_code=204)
async def remove_participant(run_id: int, participant_id: int, session: SessionDep, hub: HubDep) -> Response:
    run = svc.get_run(session, run_id)
    p = _participant(session, run, participant_id)
    if session.exec(select(Submission).where(Submission.participant_id == p.id)).first() is not None:
        raise HTTPException(409, "제출 기록이 있는 참가자는 삭제할 수 없습니다.")
    session.delete(p)
    session.commit()
    await hub.kick(run.id, participant_id)
    await hub.to_all(run.id, "participant_removed", {"id": participant_id})
    return Response(status_code=204)


@router.patch("/runs/{run_id}/boxes/{box_id}")
async def update_box(run_id: int, box_id: str, body: BoxPatch, session: SessionDep, hub: HubDep) -> dict:
    run = svc.get_run(session, run_id)
    snapshot = copy.deepcopy(run.graph_snapshot)
    target = next((b for b in snapshot.get("boxes", []) if b.get("id") == box_id), None)
    if target is None:
        raise HTTPException(404, "박스를 찾을 수 없습니다.")
    target.setdefault("config", {})["markdown"] = body.markdown
    run.graph_snapshot = snapshot
    session.add(run)
    session.commit()
    await hub.to_all(run.id, "box_content_updated", {"box_id": box_id})
    return {"box_id": box_id, "markdown": body.markdown}


@router.get("/runs/{run_id}/boxes/{box_id}/submission")
def read_submission(run_id: int, box_id: str, session: SessionDep) -> dict:
    run = svc.get_run(session, run_id)
    sub = session.exec(
        select(Submission).where(Submission.run_id == run.id, Submission.box_id == box_id)
    ).first()
    if sub is None:
        raise HTTPException(404, "제출된 코드가 없습니다.")
    return {
        "box_id": sub.box_id,
        "participant_id": sub.participant_id,
        "files": sub.files,
        "submitted_at": iso(sub.submitted_at),
    }


@router.get("/runs/{run_id}/boxes/{box_id}/versions")
def list_versions(run_id: int, box_id: str, session: SessionDep) -> list[dict]:
    run = svc.get_run(session, run_id)
    rows = session.exec(
        select(TeamVersion)
        .where(TeamVersion.run_id == run.id, TeamVersion.box_id == box_id)
        .order_by(col(TeamVersion.version_no))
    ).all()
    return [svc.version_summary(v) for v in rows]


@router.get("/runs/{run_id}/versions/{version_id}")
def read_version(run_id: int, version_id: int, session: SessionDep) -> dict:
    version = session.get(TeamVersion, version_id)
    if version is None or version.run_id != run_id:
        raise HTTPException(404, "버전을 찾을 수 없습니다.")
    return {**svc.version_summary(version), "files": version.files}


@router.get("/runs/{run_id}/files/{file_id}")
def download_run_file(run_id: int, file_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
    record = session.get(RunFile, file_id)
    if record is None or record.run_id != run_id:
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    return FileResponse(stored_path(settings.files_dir, record.stored_path), filename=record.filename)
```

`backend/app/main.py` 변경:

```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -2,5 +2,5 @@
 from fastapi import FastAPI
 
-from app.api import admin, templates
+from app.api import admin, runs, templates
 from app.config import Settings, load_settings
 from app.db import init_db, make_engine
@@ -18,5 +18,5 @@
     app.state.hub = Hub()
 
-    for module in (admin, templates):
+    for module in (admin, templates, runs):
         app.include_router(module.router)
 
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_runs.py -q` 다음 `pytest -q`
Expected: 전체 `51 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/app/services/__init__.py backend/app/services/runs.py backend/app/services/views.py backend/app/api/runs.py backend/tests/test_runs.py backend/app/main.py
git commit -m "feat(api): 회차 생성, 시작, 관리자 상태"
```

---

### Task 8: 참가자 입장, 배정, 재입장, 참가자 화면 상태

입장 코드와 이름으로 들어오고, 같은 이름으로 다시 들어오면 관리자 승인을 기다린다. 참가자에게 보낼 박스는 서버에서 거른다.

**Files:**
- Create: `backend/app/ratelimit.py`
- Create: `backend/app/api/participant.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_participants.py`
- Test: `backend/tests/test_participant_view.py`

**Interfaces:**
- Consumes: Task 5의 `ParticipantDep`, `hash_token`, `new_token`; Task 7의 `participant_state`, `can_see_box`, 관리자 배정 API
- Produces:
  - `app.ratelimit.RateLimiter(limit, window_seconds, clock=time.monotonic)`, `allow(key) -> bool`
  - `app.state.join_limiter`(IP당 분당 10회)
  - API(참가자): `POST /api/p/join {entry_code, name}` → `{status: joined|pending, token, participant_id, run_id}`, `GET /api/p/state`, `GET /api/p/files/{file_id}`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_participants.py`:

```python
from app.ratelimit import RateLimiter
from tests.helpers import assign, join, open_run, tok


def test_join_and_admin_sees_participant(admin_client):
    run = open_run(admin_client)
    joined = join(admin_client, run["entry_code"].lower(), " 김철수 ")
    assert joined["status"] == "joined"
    people = admin_client.get(f"/api/runs/{run['id']}/state").json()["participants"]
    assert [(p["name"], p["assigned_box_id"], p["is_leader"]) for p in people] == [("김철수", None, False)]


def test_join_wrong_code(client):
    r = client.post("/api/p/join", json={"entry_code": "ZZZZZZ", "name": "x"})
    assert r.status_code == 404


def test_join_finished_run_rejected(admin_client):
    run = open_run(admin_client)
    admin_client.post(f"/api/runs/{run['id']}/finish")
    r = admin_client.post("/api/p/join", json={"entry_code": run["entry_code"], "name": "x"})
    assert r.status_code == 404


def test_participant_token_required(client):
    assert client.get("/api/p/state").status_code == 401
    assert client.get("/api/p/state", headers=tok("bad")).status_code == 401


def test_assign_and_leader(admin_client):
    run = open_run(admin_client)
    p1 = join(admin_client, run["entry_code"], "가")["participant_id"]
    p2 = join(admin_client, run["entry_code"], "나")["participant_id"]
    assign(admin_client, run["id"], p1, "a", leader=True)
    assign(admin_client, run["id"], p2, "b", leader=True)
    people = {p["id"]: p for p in admin_client.get(f"/api/runs/{run['id']}/state").json()["participants"]}
    assert people[p1]["assigned_box_id"] == "a" and people[p1]["is_leader"] is False
    assert people[p2]["assigned_box_id"] == "b" and people[p2]["is_leader"] is True


def test_assign_rejects_taken_or_non_personal_box(admin_client):
    run = open_run(admin_client)
    p1 = join(admin_client, run["entry_code"], "가")["participant_id"]
    p2 = join(admin_client, run["entry_code"], "나")["participant_id"]
    assign(admin_client, run["id"], p1, "a")
    url = f"/api/runs/{run['id']}/participants/{p2}"
    assert admin_client.patch(url, json={"assigned_box_id": "a"}).status_code == 409
    assert admin_client.patch(url, json={"assigned_box_id": "team"}).status_code == 422
    # 배정 해제 후에는 다른 사람이 받을 수 있다
    assign(admin_client, run["id"], p1, None)
    assign(admin_client, run["id"], p2, "a")


def test_rejoin_needs_admin_approval(admin_client):
    run = open_run(admin_client)
    first = join(admin_client, run["entry_code"], "가")
    second = join(admin_client, run["entry_code"], "가")
    assert second["status"] == "pending"
    assert second["participant_id"] == first["participant_id"]
    assert admin_client.get("/api/p/state", headers=tok(second["token"])).status_code == 409
    people = admin_client.get(f"/api/runs/{run['id']}/state").json()["participants"]
    assert people[0]["rejoin_requested"] is True

    r = admin_client.post(f"/api/runs/{run['id']}/participants/{first['participant_id']}/approve-rejoin")
    assert r.status_code == 200
    assert admin_client.get("/api/p/state", headers=tok(second["token"])).status_code == 200
    assert admin_client.get("/api/p/state", headers=tok(first["token"])).status_code == 401
    again = admin_client.post(f"/api/runs/{run['id']}/participants/{first['participant_id']}/approve-rejoin")
    assert again.status_code == 409


def test_remove_participant(admin_client):
    run = open_run(admin_client)
    p = join(admin_client, run["entry_code"], "가")
    assert admin_client.delete(f"/api/runs/{run['id']}/participants/{p['participant_id']}").status_code == 204
    assert admin_client.get(f"/api/runs/{run['id']}/state").json()["participants"] == []


def test_join_rate_limited(client):
    for _ in range(10):
        assert client.post("/api/p/join", json={"entry_code": "ZZZZZZ", "name": "x"}).status_code == 404
    assert client.post("/api/p/join", json={"entry_code": "ZZZZZZ", "name": "x"}).status_code == 429


def test_rate_limiter_window():
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    assert limiter.allow("ip") and limiter.allow("ip")
    assert not limiter.allow("ip")
    assert limiter.allow("other")
    now[0] = 60.0
    assert limiter.allow("ip")
```

`backend/tests/test_participant_view.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_participants.py tests/test_participant_view.py -q`
Expected: FAIL — `404 Not Found`

- [ ] **Step 3: 구현**

`backend/app/ratelimit.py`:

```python
"""IP별 시도 횟수 제한 (메모리, 워커 1개 전제)."""
import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True
```

`backend/app/api/participant.py`:

```python
"""참가자 API. 인증은 X-Participant-Token 헤더."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import select

from app.auth import hash_token, new_token
from app.deps import HubDep, ParticipantDep, SessionDep, SettingsDep
from app.models import Participant, Run, RunFile
from app.services import runs as svc
from app.services.views import can_see_box, participant_out, participant_state
from app.storage import stored_path

router = APIRouter(prefix="/api/p", tags=["participant"])


class JoinIn(BaseModel):
    entry_code: str = Field(min_length=1, max_length=12)
    name: str = Field(min_length=1, max_length=30)


@router.post("/join")
async def join(body: JoinIn, request: Request, session: SessionDep, hub: HubDep) -> dict:
    client_key = request.client.host if request.client else "unknown"
    if not request.app.state.join_limiter.allow(client_key):
        raise HTTPException(429, "입장 시도가 너무 많습니다. 잠시 뒤 다시 시도하세요.")
    run = session.exec(select(Run).where(Run.entry_code == body.entry_code.strip().upper())).first()
    if run is None or run.status == "finished":
        raise HTTPException(404, "입장 코드를 확인하세요.")
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "이름을 입력하세요.")
    token = new_token()
    existing = session.exec(
        select(Participant).where(Participant.run_id == run.id, Participant.name == name)
    ).first()
    if existing is not None:
        existing.rejoin_token_hash = hash_token(token)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        await hub.to_admins(run.id, "participant_updated", participant_out(existing, hub.online(run.id)))
        return {"status": "pending", "token": token, "participant_id": existing.id, "run_id": run.id}
    participant = Participant(run_id=run.id, name=name, token_hash=hash_token(token))
    session.add(participant)
    session.commit()
    session.refresh(participant)
    await hub.to_admins(run.id, "participant_updated", participant_out(participant, hub.online(run.id)))
    return {"status": "joined", "token": token, "participant_id": participant.id, "run_id": run.id}


@router.get("/state")
def state(me: ParticipantDep, session: SessionDep) -> dict:
    return participant_state(session, svc.get_run(session, me.run_id), me)


@router.get("/files/{file_id}")
def download(file_id: int, me: ParticipantDep, session: SessionDep, settings: SettingsDep) -> FileResponse:
    record = session.get(RunFile, file_id)
    run = svc.get_run(session, me.run_id)
    if record is None or record.run_id != run.id or not can_see_box(session, run, me, record.box_id):
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    return FileResponse(stored_path(settings.files_dir, record.stored_path), filename=record.filename)
```

`backend/app/main.py` 변경:

```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -2,7 +2,8 @@
 from fastapi import FastAPI
 
-from app.api import admin, runs, templates
+from app.api import admin, participant, runs, templates
 from app.config import Settings, load_settings
 from app.db import init_db, make_engine
+from app.ratelimit import RateLimiter
 from app.ws.hub import Hub
 
@@ -17,6 +18,7 @@
     app.state.engine = engine
     app.state.hub = Hub()
+    app.state.join_limiter = RateLimiter(limit=10, window_seconds=60)
 
-    for module in (admin, templates, runs):
+    for module in (admin, templates, runs, participant):
         app.include_router(module.router)
 
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_participants.py tests/test_participant_view.py -q` 다음 `pytest -q`
Expected: 전체 `65 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/app/ratelimit.py backend/app/api/participant.py backend/tests/test_participants.py backend/tests/test_participant_view.py backend/app/main.py
git commit -m "feat(api): 참가자 입장과 참가자 상태"
```

---

### Task 9: 개인 제출과 관리자 승인

개인 박스 제출(박스가 닫히기 전까지 재제출, 마지막 것만 보관)과 승인 연결선 처리. 미제출 파트가 있으면 `confirm: true` 없이는 409로 확인을 요구한다.

**Files:**
- Create: `backend/app/services/progress.py`
- Modify: `backend/app/api/runs.py`
- Modify: `backend/app/api/participant.py`
- Test: `backend/tests/test_progress.py`

**Interfaces:**
- Consumes: Task 7의 `advance_run`, `flow_state`, `graph_of`, `state_rows`, `require_running`; Task 3의 `can_approve`
- Produces:
  - `app.services.progress`: `MAX_CODE_BYTES`, `check_files(files, expected) -> dict`, `async submit_personal(session, hub, run, me, box_id, files)`, `async approve_edges(session, hub, run, edge_ids, confirm)`
  - API: `POST /api/p/boxes/{box_id}/submit {files}`, `POST /api/runs/{id}/approvals {edge_ids, confirm}`(응답은 `admin_state`)
  - 웹소켓 이벤트: `submission_received`(관리자만), `edge_approved`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_progress.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_progress.py -q`
Expected: FAIL — `404 Not Found` / `405 Method Not Allowed`

- [ ] **Step 3: 구현**

`backend/app/services/progress.py`:

```python
"""진행 동작: 개인 제출, 연결선 승인, 팀 편집. REST API와 웹소켓이 함께 쓴다."""
from fastapi import HTTPException
from sqlmodel import Session, select

from app.engine.flow import OPEN, can_approve
from app.models import EdgeApproval, Participant, Run, Submission, iso, utcnow
from app.services.runs import advance_run, flow_state, graph_of, require_running, state_rows
from app.ws.hub import Hub

MAX_CODE_BYTES = 200 * 1024


def check_files(files: object, expected: set[str]) -> dict[str, str]:
    """제출 파일이 {이름: 코드} 형식이고 이름이 expected와 같으며 크기 제한을 지키는지 확인한다."""
    if not isinstance(files, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in files.items()
    ):
        raise HTTPException(422, "파일 형식이 올바르지 않습니다.")
    if set(files) != expected:
        raise HTTPException(422, f"제출 파일은 {', '.join(sorted(expected))} 이어야 합니다.")
    for name, code in files.items():
        if len(code.encode("utf-8")) > MAX_CODE_BYTES:
            raise HTTPException(413, f"{name} 파일이 200KB를 넘습니다.")
    return dict(files)


def _open_box(session: Session, run: Run, box_id: str) -> None:
    row = state_rows(session, run.id).get(box_id)
    if row is None or row.state != OPEN:
        raise HTTPException(409, "이 단계는 닫혔습니다.")


async def submit_personal(
    session: Session, hub: Hub, run: Run, me: Participant, box_id: str, files: object
) -> Submission:
    require_running(run)
    box = graph_of(run).boxes.get(box_id)
    if box is None or box.type != "personal":
        raise HTTPException(404, "개인 박스를 찾을 수 없습니다.")
    if me.assigned_box_id != box_id:
        raise HTTPException(403, "내 파트가 아닙니다.")
    _open_box(session, run, box_id)
    clean = check_files(files, {f.name for f in box.files})
    now = utcnow()
    sub = session.exec(
        select(Submission).where(Submission.run_id == run.id, Submission.box_id == box_id)
    ).first()
    if sub is None:
        sub = Submission(run_id=run.id, box_id=box_id, participant_id=me.id, files=clean, submitted_at=now)
    else:
        sub.files, sub.participant_id, sub.submitted_at = clean, me.id, now
    me.last_active_at = now
    session.add(sub)
    session.add(me)
    session.commit()
    session.refresh(sub)
    await hub.to_admins(
        run.id,
        "submission_received",
        {"box_id": box_id, "participant_id": me.id, "submitted_at": iso(now)},
    )
    await advance_run(session, hub, run)
    return sub


async def approve_edges(
    session: Session, hub: Hub, run: Run, edge_ids: list[str], confirm: bool
) -> None:
    require_running(run)
    graph = graph_of(run)
    fs = flow_state(session, run)
    edges = []
    for edge_id in edge_ids:
        edge = graph.edge(edge_id)
        if edge is None or edge.mode != "approval":
            raise HTTPException(404, f"승인 연결선이 아닙니다: {edge_id}")
        if edge_id in fs.approved:
            continue
        if not can_approve(edge, fs.states):
            raise HTTPException(409, f"아직 승인할 수 없는 연결선입니다: {edge_id}")
        edges.append(edge)
    unsubmitted = [
        e.source for e in edges
        if graph.boxes[e.source].type == "personal" and e.source not in fs.submitted
    ]
    if unsubmitted and not confirm:
        raise HTTPException(
            409,
            {
                "code": "unsubmitted",
                "box_ids": unsubmitted,
                "message": f"아직 제출하지 않은 파트가 {len(unsubmitted)}개 있습니다.",
            },
        )
    now = utcnow()
    for edge in edges:
        session.add(EdgeApproval(run_id=run.id, edge_id=edge.id, approved_at=now))
    session.commit()
    for edge in edges:
        await hub.to_all(run.id, "edge_approved", {"edge_id": edge.id})
    await advance_run(session, hub, run)
```

`backend/app/api/runs.py` 변경:

```diff
--- a/backend/app/api/runs.py
+++ b/backend/app/api/runs.py
@@ -21,4 +21,5 @@
     utcnow,
 )
+from app.services import progress
 from app.services import runs as svc
 from app.services.views import admin_state, participant_out, run_summary
@@ -250,2 +251,14 @@
         raise HTTPException(404, "파일을 찾을 수 없습니다.")
     return FileResponse(stored_path(settings.files_dir, record.stored_path), filename=record.filename)
+
+
+class ApprovalIn(BaseModel):
+    edge_ids: list[str] = Field(min_length=1)
+    confirm: bool = False
+
+
+@router.post("/runs/{run_id}/approvals")
+async def approve(run_id: int, body: ApprovalIn, session: SessionDep, hub: HubDep) -> dict:
+    run = svc.get_run(session, run_id)
+    await progress.approve_edges(session, hub, run, body.edge_ids, body.confirm)
+    return admin_state(session, run, hub.online(run.id))
```

`backend/app/api/participant.py` 변경:

```diff
--- a/backend/app/api/participant.py
+++ b/backend/app/api/participant.py
@@ -7,5 +7,6 @@
 from app.auth import hash_token, new_token
 from app.deps import HubDep, ParticipantDep, SessionDep, SettingsDep
-from app.models import Participant, Run, RunFile
+from app.models import Participant, Run, RunFile, iso
+from app.services import progress
 from app.services import runs as svc
 from app.services.views import can_see_box, participant_out, participant_state
@@ -62,2 +63,13 @@
         raise HTTPException(404, "파일을 찾을 수 없습니다.")
     return FileResponse(stored_path(settings.files_dir, record.stored_path), filename=record.filename)
+
+
+class FilesIn(BaseModel):
+    files: dict[str, str]
+
+
+@router.post("/boxes/{box_id}/submit")
+async def submit(box_id: str, body: FilesIn, me: ParticipantDep, session: SessionDep, hub: HubDep) -> dict:
+    run = svc.get_run(session, me.run_id)
+    sub = await progress.submit_personal(session, hub, run, me, box_id, body.files)
+    return {"box_id": sub.box_id, "submitted_at": iso(sub.submitted_at)}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_progress.py -q` 다음 `pytest -q`
Expected: 전체 `74 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/app/services/progress.py backend/tests/test_progress.py backend/app/api/runs.py backend/app/api/participant.py
git commit -m "feat(api): 개인 제출과 승인"
```

---

### Task 10: 팀 단계: 팀장 편집, 버전, 최종 제출

팀 박스는 열릴 때 앞 개인 박스 제출본으로 채워진다(Task 7 `apply_transition`). 팀장만 고치고, 저장할 때마다 버전이 쌓이며, 최종 제출하면 결과 박스가 열리고 회차가 끝난다.

**Files:**
- Modify: `backend/app/services/progress.py`
- Modify: `backend/app/api/participant.py`
- Test: `backend/tests/test_team.py`

**Interfaces:**
- Consumes: Task 9의 `check_files`, `_open_box`; Task 7의 `version_summary`, `draft_out`, `advance_run`
- Produces:
  - `app.services.progress`: `save_team_draft(session, run, me, box_id, files) -> TeamDraft`(동기), `async save_team_version(session, hub, run, me, box_id, files, final) -> TeamVersion`
  - API: `PUT /api/p/boxes/{box_id}/draft {files}`, `POST /api/p/boxes/{box_id}/versions {files, final}`
  - 웹소켓 이벤트: `team_draft`(팀원에게), `team_version_saved`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_team.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_team.py -q`
Expected: FAIL — `404 Not Found`

- [ ] **Step 3: 구현**

`backend/app/services/progress.py` 변경:

```diff
--- a/backend/app/services/progress.py
+++ b/backend/app/services/progress.py
@@ -1,9 +1,17 @@
 """진행 동작: 개인 제출, 연결선 승인, 팀 편집. REST API와 웹소켓이 함께 쓴다."""
 from fastapi import HTTPException
-from sqlmodel import Session, select
+from sqlmodel import Session, col, select
 
 from app.engine.flow import OPEN, can_approve
-from app.models import EdgeApproval, Participant, Run, Submission, iso, utcnow
-from app.services.runs import advance_run, flow_state, graph_of, require_running, state_rows
+from app.engine.graph import Box
+from app.models import EdgeApproval, Participant, Run, Submission, TeamDraft, TeamVersion, iso, utcnow
+from app.services.runs import (
+    advance_run,
+    flow_state,
+    graph_of,
+    require_running,
+    state_rows,
+    version_summary,
+)
 from app.ws.hub import Hub
 
@@ -100,2 +108,58 @@
         await hub.to_all(run.id, "edge_approved", {"edge_id": edge.id})
     await advance_run(session, hub, run)
+
+
+def _team_box_for_leader(session: Session, run: Run, me: Participant, box_id: str) -> Box:
+    require_running(run)
+    box = graph_of(run).boxes.get(box_id)
+    if box is None or box.type != "team":
+        raise HTTPException(404, "팀 박스를 찾을 수 없습니다.")
+    if not me.is_leader:
+        raise HTTPException(403, "팀장만 편집할 수 있습니다.")
+    _open_box(session, run, box_id)
+    return box
+
+
+def save_team_draft(
+    session: Session, run: Run, me: Participant, box_id: str, files: object
+) -> TeamDraft:
+    _team_box_for_leader(session, run, me, box_id)
+    draft = session.exec(
+        select(TeamDraft).where(TeamDraft.run_id == run.id, TeamDraft.box_id == box_id)
+    ).first()
+    if draft is None:
+        raise HTTPException(409, "팀 박스가 아직 준비되지 않았습니다.")
+    draft.files = check_files(files, set(draft.files))
+    draft.updated_at = utcnow()
+    me.last_active_at = draft.updated_at
+    session.add(draft)
+    session.add(me)
+    session.commit()
+    session.refresh(draft)
+    return draft
+
+
+async def save_team_version(
+    session: Session, hub: Hub, run: Run, me: Participant, box_id: str, files: object, final: bool
+) -> TeamVersion:
+    draft = save_team_draft(session, run, me, box_id, files)
+    last = session.exec(
+        select(TeamVersion)
+        .where(TeamVersion.run_id == run.id, TeamVersion.box_id == box_id)
+        .order_by(col(TeamVersion.version_no).desc())
+    ).first()
+    version = TeamVersion(
+        run_id=run.id,
+        box_id=box_id,
+        version_no=(last.version_no + 1) if last else 1,
+        files=dict(draft.files),
+        saved_at=utcnow(),
+        is_final=final,
+    )
+    session.add(version)
+    session.commit()
+    session.refresh(version)
+    await hub.to_all(run.id, "team_version_saved", version_summary(version))
+    if final:
+        await advance_run(session, hub, run)
+    return version
```

`backend/app/api/participant.py` 변경:

```diff
--- a/backend/app/api/participant.py
+++ b/backend/app/api/participant.py
@@ -74,2 +74,21 @@
     sub = await progress.submit_personal(session, hub, run, me, box_id, body.files)
     return {"box_id": sub.box_id, "submitted_at": iso(sub.submitted_at)}
+
+
+class VersionIn(FilesIn):
+    final: bool = False
+
+
+@router.put("/boxes/{box_id}/draft")
+async def save_draft(box_id: str, body: FilesIn, me: ParticipantDep, session: SessionDep, hub: HubDep) -> dict:
+    run = svc.get_run(session, me.run_id)
+    draft = progress.save_team_draft(session, run, me, box_id, body.files)
+    await hub.to_participants(run.id, "team_draft", svc.draft_out(draft), exclude=me.id)
+    return svc.draft_out(draft)
+
+
+@router.post("/boxes/{box_id}/versions", status_code=201)
+async def save_version(box_id: str, body: VersionIn, me: ParticipantDep, session: SessionDep, hub: HubDep) -> dict:
+    run = svc.get_run(session, me.run_id)
+    version = await progress.save_team_version(session, hub, run, me, box_id, body.files, body.final)
+    return svc.version_summary(version)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_team.py -q` 다음 `pytest -q`
Expected: 전체 `78 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/tests/test_team.py backend/app/services/progress.py backend/app/api/participant.py
git commit -m "feat(api): 팀장 편집, 버전, 최종 제출"
```

---

### Task 11: 웹소켓 엔드포인트

관리자(쿠키)와 참가자(`?token=`)가 회차별로 접속한다. 접속·종료 시 관리자에게 상태를 알리고, `typing`과 팀장의 `team_draft`를 받는다.

**Files:**
- Create: `backend/app/api/ws.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_ws.py`

**Interfaces:**
- Consumes: Task 4의 `Hub`, `Conn`; Task 5의 `check_admin_cookie`, `hash_token`; Task 10의 `save_team_draft`
- Produces:
  - `WS /ws/runs/{run_id}`: 메시지 `{event, data}`; 클라이언트 → `{type: ping|typing|team_draft}`; 인증 실패 close 4401, 없는 회차 4404

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_ws.py`:

```python
import pytest
from starlette.websockets import WebSocketDisconnect

from app.auth import ADMIN_COOKIE
from tests.helpers import approve_all, open_run, started_parking_run, submit


def admin_ws(client, run_id: int):
    cookie = client.cookies.get(ADMIN_COOKIE)
    return client.websocket_connect(f"/ws/runs/{run_id}", headers={"cookie": f"{ADMIN_COOKIE}={cookie}"})


def participant_ws(client, run_id: int, token: str):
    return client.websocket_connect(f"/ws/runs/{run_id}?token={token}")


def receive_until(ws, event: str, limit: int = 20) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message["event"] == event:
            return message["data"]
    raise AssertionError(f"{event} 이벤트를 받지 못했습니다.")


def test_rejects_unauthenticated(admin_client):
    run = open_run(admin_client)
    with pytest.raises(WebSocketDisconnect) as bad_token:
        with participant_ws(admin_client, run["id"], "bad"):
            pass
    assert bad_token.value.code == 4401
    with pytest.raises(WebSocketDisconnect) as no_run:
        with admin_ws(admin_client, 9999):
            pass
    assert no_run.value.code == 4404
    admin_client.post("/api/admin/logout")
    with pytest.raises(WebSocketDisconnect) as no_cookie:
        with admin_client.websocket_connect(f"/ws/runs/{run['id']}"):
            pass
    assert no_cookie.value.code == 4401


def test_ping(admin_client):
    run = open_run(admin_client)
    with admin_ws(admin_client, run["id"]) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"event": "pong", "data": {}}


def test_admin_sees_presence_typing_and_submission(admin_client):
    ctx = started_parking_run(admin_client)
    run_id, token, pid = ctx["run"]["id"], ctx["tokens"]["a"], ctx["ids"]["a"]
    with admin_ws(admin_client, run_id) as admin:
        with participant_ws(admin_client, run_id, token) as p:
            online = receive_until(admin, "participant_updated")
            assert (online["id"], online["online"]) == (pid, True)
            assert admin_client.get(f"/api/runs/{run_id}/state").json()["participants"][0]["online"] is True

            p.send_json({"type": "typing"})
            typing = receive_until(admin, "participant_updated")
            assert typing["typing"] is True

            submit(admin_client, token, "a", "A")
            got = receive_until(admin, "submission_received")
            assert (got["box_id"], got["participant_id"]) == ("a", pid)
        offline = receive_until(admin, "participant_updated")
        assert offline["online"] is False


def test_box_state_changes_broadcast(admin_client):
    ctx = started_parking_run(admin_client)
    run_id = ctx["run"]["id"]
    with participant_ws(admin_client, run_id, ctx["tokens"]["b"]) as p:
        approve_all(admin_client, run_id)
        changes = [receive_until(p, "box_state_changed") for _ in range(5)]
        assert {(c["box_id"], c["state"]) for c in changes} == {
            ("team", "open"), ("a", "closed"), ("b", "closed"), ("c", "closed"), ("d", "closed"),
        }


def test_leader_draft_reaches_members(admin_client):
    ctx = started_parking_run(admin_client)
    run_id = ctx["run"]["id"]
    approve_all(admin_client, run_id)
    files = admin_client.get("/api/p/state", headers={"X-Participant-Token": ctx["tokens"]["a"]}).json()["team"]["team"]["files"]
    files["e_main.py"] = "live"
    with participant_ws(admin_client, run_id, ctx["tokens"]["b"]) as member:
        with participant_ws(admin_client, run_id, ctx["tokens"]["a"]) as leader:
            leader.send_json({"type": "team_draft", "box_id": "team", "files": files})
            draft = receive_until(member, "team_draft")
            assert draft["files"]["e_main.py"] == "live"
        with participant_ws(admin_client, run_id, ctx["tokens"]["c"]) as not_leader:
            not_leader.send_json({"type": "team_draft", "box_id": "team", "files": files})
            error = receive_until(not_leader, "error")
            assert error["detail"] == "팀장만 편집할 수 있습니다."
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_ws.py -q`
Expected: FAIL — `WebSocketDisconnect`(경로 없음)

- [ ] **Step 3: 구현**

`backend/app/api/ws.py`:

```python
"""회차 웹소켓. 관리자는 세션 쿠키, 참가자는 ?token= 으로 인증한다.

서버 → 클라이언트: {"event": 이름, "data": {...}}
클라이언트 → 서버: {"type": "ping"} | {"type": "typing"} | {"type": "team_draft", "box_id": ..., "files": {...}}
"""
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.auth import ADMIN_COOKIE, check_admin_cookie, hash_token
from app.models import Participant, Run, utcnow
from app.services import progress
from app.services import runs as svc
from app.services.views import participant_out
from app.ws.hub import Conn, Hub

router = APIRouter()

TYPING_WRITE_SECONDS = 5


async def _notify_admins(engine: Engine, hub: Hub, run_id: int, participant_id: int) -> None:
    with Session(engine) as session:
        p = session.get(Participant, participant_id)
        if p is not None:
            await hub.to_admins(run_id, "participant_updated", participant_out(p, hub.online(run_id)))


async def _handle(
    message: dict, websocket: WebSocket, engine: Engine, hub: Hub, run_id: int, participant_id: int | None
) -> None:
    kind = message.get("type")
    if kind == "ping":
        await websocket.send_json({"event": "pong", "data": {}})
        return
    if participant_id is None:
        return
    with Session(engine) as session:
        me = session.get(Participant, participant_id)
        run = session.get(Run, run_id)
        if me is None or run is None:
            return
        if kind == "typing":
            now = utcnow()
            if me.last_active_at is None or (now - me.last_active_at).total_seconds() >= TYPING_WRITE_SECONDS:
                me.last_active_at = now
                session.add(me)
                session.commit()
                session.refresh(me)
                await hub.to_admins(run_id, "participant_updated", participant_out(me, hub.online(run_id)))
        elif kind == "team_draft":
            try:
                draft = progress.save_team_draft(session, run, me, str(message.get("box_id")), message.get("files"))
            except HTTPException as exc:
                await websocket.send_json({"event": "error", "data": {"detail": exc.detail}})
                return
            await hub.to_participants(run_id, "team_draft", svc.draft_out(draft), exclude=participant_id)


@router.websocket("/ws/runs/{run_id}")
async def run_socket(websocket: WebSocket, run_id: int) -> None:
    app = websocket.app
    settings, engine, hub = app.state.settings, app.state.engine, app.state.hub
    token = websocket.query_params.get("token")
    participant_id: int | None = None
    token_hash: str | None = None
    with Session(engine) as session:
        if session.get(Run, run_id) is None:
            await websocket.close(code=4404)
            return
        if token:
            token_hash = hash_token(token)
            p = session.exec(
                select(Participant).where(Participant.run_id == run_id, Participant.token_hash == token_hash)
            ).first()
            if p is None:
                await websocket.close(code=4401)
                return
            participant_id = p.id
        elif not check_admin_cookie(settings, websocket.cookies.get(ADMIN_COOKIE)):
            await websocket.close(code=4401)
            return

    await websocket.accept()
    conn = Conn(
        socket=websocket,
        role="participant" if participant_id is not None else "admin",
        participant_id=participant_id,
        token_hash=token_hash,
    )
    hub.connect(run_id, conn)
    if participant_id is not None:
        await _notify_admins(engine, hub, run_id, participant_id)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                await _handle(message, websocket, engine, hub, run_id, participant_id)
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(run_id, conn)
        if participant_id is not None:
            await _notify_admins(engine, hub, run_id, participant_id)
```

`backend/app/main.py` 변경:

```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -2,5 +2,5 @@
 from fastapi import FastAPI
 
-from app.api import admin, participant, runs, templates
+from app.api import admin, participant, runs, templates, ws
 from app.config import Settings, load_settings
 from app.db import init_db, make_engine
@@ -20,5 +20,5 @@
     app.state.join_limiter = RateLimiter(limit=10, window_seconds=60)
 
-    for module in (admin, templates, runs, participant):
+    for module in (admin, templates, runs, participant, ws):
         app.include_router(module.router)
 
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_ws.py -q` 다음 `pytest -q`
Expected: 전체 `83 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/app/api/ws.py backend/tests/test_ws.py backend/app/main.py
git commit -m "feat(ws): 회차 웹소켓"
```

---

### Task 12: 전체 시나리오 테스트와 실행 안내

주차장 과제로 회차를 처음부터 끝까지 API만으로 돌려 각 부분이 맞물리는지 확인한다.

**Files:**
- Create: `backend/README.md`
- Test: `backend/tests/test_scenario.py`

**Interfaces:**
- Consumes: 앞 작업 전체
- Produces:
  - `backend/README.md`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_scenario.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `pytest tests/test_scenario.py -q`
Expected: FAIL — (새 코드 없이 통과해야 정상. 실패하면 앞 작업의 결함)

- [ ] **Step 3: 구현**

`backend/README.md`:

````markdown
# backend

FastAPI 서버. 설계는 `docs/superpowers/specs/2026-11-08-coding-test-web-design.md`.

## 개발

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## 실행

```bash
ADMIN_PASSWORD=change-me SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") DATA_DIR=./data \
  uvicorn app.main:create_app --factory --workers 1 --port 8000
```

- 워커는 반드시 1개. 웹소켓 연결과 입장 시도 제한을 메모리에 둔다.
- HTTPS 프록시 뒤에서는 `COOKIE_SECURE=1`.
- API 문서: http://localhost:8000/docs
````

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_scenario.py -q` 다음 `pytest -q`
Expected: 전체 `84 passed`

- [ ] **Step 5: 커밋**

```bash
git add backend/tests/test_scenario.py backend/README.md
git commit -m "test: 주차장 전체 시나리오와 실행 안내"
```

---

## 완료 기준

- `pytest -q` → `84 passed`
- `ADMIN_PASSWORD=x SECRET_KEY=y DATA_DIR=./data uvicorn app.main:create_app --factory --workers 1` 실행 후 `GET /api/health` → `{"ok": true}`, `/docs`에서 API 목록 확인

## 다음 계획

- 계획 2: 프런트엔드 — 관리자 5개 화면(로그인, 시험장 목록, 에디터, 진행, 결과)과 참가자 3개 화면(입장/대기실, 작업, 종료). 이 계획의 API와 이벤트 이름을 그대로 쓴다.
- 계획 3: 배포와 마무리 — 멀티 스테이지 Dockerfile, compose 예시, FastAPI 정적 파일 서빙, Alembic, 주차장 시드(정답 코드 제외), Playwright 전체 흐름.
