"""주차장 관리 프로그램 과제를 시험장으로 등록한다.

문제 파일은 저장소에 두지 않는다. 학생용 문제 폴더(a_entry.py ~ e_main.py)를 읽어
배포된 서버의 관리자 API로 시험장을 만든다.

사용:
    python scripts/seed_parking.py --url https://cotest.ssenu.cloud --password '...' --dir "C:/.../student"

backend 가상환경(httpx 포함)에서 실행한다.
"""
import argparse
import ast
import sys
from pathlib import Path

import httpx

PARTS = [
    ("a", "a_entry.py", "A. 입차 등록"),
    ("b", "b_exit.py", "B. 출차 처리"),
    ("c", "c_fee.py", "C. 요금 계산"),
    ("d", "d_status.py", "D. 주차 현황"),
]
TEAM = ("team", "e_main.py", "E. 통합 (팀)")

STORY = """# 주차장 관리 프로그램

작은 주차장을 관리하는 파이썬 프로그램을 팀이 함께 만듭니다.

## 진행 순서
1. **개인 단계**: 각자 맡은 파트(A~D) 하나를 풉니다. 파일 아래쪽 테스트가 모두 통과하도록 `# TODO` 부분을 채우고 제출하세요. 단계가 닫히기 전까지 다시 제출할 수 있습니다.
2. **관리자 확인**: 관리자가 제출을 확인하고 다음 단계를 엽니다.
3. **팀 단계**: 모두의 코드가 한 화면에 모입니다. 팀장이 대표로 `e_main.py`를 완성하고, 필요하면 앞 단계 파일도 고쳐서 최종 제출합니다.

## 공통 데이터
```python
lot = {"12가3456": "09:00", "34나5678": "10:15"}
```
- 키: 차량번호(문자열), 값: 입차 시각(`"HH:MM"`, 항상 두 자리)
- A가 lot에 차를 넣고, B가 빼면서 주차한 분을 돌려주고, C가 그 분으로 요금을 내고, D가 lot을 현황 문자열로 만듭니다. E는 넷을 묶습니다.

## 테스트 실행
각 파일을 그대로 실행하면 테스트 결과가 나옵니다. 예: `python a_entry.py`
"""

TEAM_EXTRA = """
## E-3. 추가 요구사항: 정기권
`e_main.py` 맨 아래 E-3 테스트를 통과하도록 앞 단계 코드까지 고칩니다.
- 정기권 차량은 만차여도 입차합니다(`car_in(..., is_pass=True)`). 번호 형식과 중복 검사는 그대로 합니다.
- 정원을 넘겨도 빈자리는 음수가 되지 않습니다. 현황은 `(2/1)`, `빈자리: 0 (만차)`처럼 나옵니다.
- 정기권 차량의 출차 요금은 0원입니다(`process_records(..., passes={...})`).
"""


def header_comment(source: str) -> str:
    lines = []
    for line in source.splitlines():
        if not line.startswith("#"):
            if lines:
                break
            continue
        text = line.lstrip("#").strip()
        if text and set(text) != {"="}:
            lines.append(text)
    return "\n".join(lines)


def todo_functions(source: str) -> list[tuple[str, str]]:
    """'# TODO'가 들어 있는 함수의 (시그니처, docstring)."""
    tree = ast.parse(source)
    lines = source.splitlines()
    out = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        body = "\n".join(lines[node.lineno - 1: node.end_lineno])
        if "TODO" not in body:
            continue
        signature = lines[node.lineno - 1].strip().removeprefix("def ").rstrip(":")
        out.append((signature, (ast.get_docstring(node) or "").strip()))
    return out


def part_markdown(title: str, filename: str, source: str) -> str:
    md = [f"# {title}", "", f"파일: `{filename}`", ""]
    header = header_comment(source)
    if header:
        md += ["```", header, "```", ""]
    md.append("## 구현할 함수")
    for signature, doc in todo_functions(source):
        md += ["", f"### `{signature}`", "```", doc, "```"]
    md += ["", f"다 했으면 `python {filename}`로 테스트를 돌려 모두 통과하는지 확인하고 제출하세요."]
    return "\n".join(md)


def box(box_id: str, box_type: str, title: str, x: int, y: int, markdown: str = "", files=()) -> dict:
    return {
        "id": box_id,
        "type": box_type,
        "title": title,
        "position": {"x": x, "y": y},
        "config": {
            "markdown": markdown,
            "attachments_enabled": False,
            "editor": {"files": [{"name": n, "starter": s} for n, s in files]},
        },
    }


def build_graph(folder: Path) -> dict:
    def read(name: str) -> str:
        path = folder / name
        if not path.is_file():
            sys.exit(f"{path} 파일이 없습니다.")
        return path.read_text(encoding="utf-8")

    boxes = [box("story", "common", "스토리", 0, 180, STORY)]
    for i, (box_id, filename, title) in enumerate(PARTS):
        source = read(filename)
        boxes.append(box(box_id, "personal", title, 280, i * 120, part_markdown(title, filename, source),
                         [(filename, source)]))
    team_id, team_file, team_title = TEAM
    team_source = read(team_file)
    boxes.append(box(team_id, "team", team_title, 560, 180,
                     part_markdown(team_title, team_file, team_source) + "\n" + TEAM_EXTRA,
                     [(team_file, team_source)]))
    boxes.append(box("result", "result", "결과", 840, 180))

    edges = [{"id": f"story-{p}", "source": "story", "target": p, "mode": "auto"} for p, _, _ in PARTS]
    edges += [{"id": f"{p}-team", "source": p, "target": "team", "mode": "approval"} for p, _, _ in PARTS]
    edges.append({"id": "team-result", "source": "team", "target": "result", "mode": "auto"})
    return {"boxes": boxes, "edges": edges}


def main() -> None:
    parser = argparse.ArgumentParser(description="주차장 과제를 시험장으로 등록한다.")
    parser.add_argument("--url", required=True, help="사이트 주소, 예: https://cotest.ssenu.cloud")
    parser.add_argument("--password", required=True, help="관리자 비밀번호")
    parser.add_argument("--dir", required=True, type=Path, help="학생용 문제 폴더")
    parser.add_argument("--name", default="주차장 관리 프로그램", help="시험장 이름")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    graph = build_graph(args.dir)
    with httpx.Client(base_url=base, headers={"Origin": base}, timeout=30) as client:
        login = client.post("/api/admin/login", json={"password": args.password})
        if login.status_code != 200:
            sys.exit(f"로그인 실패: {login.status_code} {login.text}")
        res = client.post("/api/templates", json={
            "name": args.name,
            "description": "개인 A~D → 관리자 승인 → 팀 E(통합, 정기권)",
            "graph": graph,
        })
        res.raise_for_status()
        template = res.json()
    if template["valid"]:
        print(f"등록했습니다: {base}/admin/templates/{template['id']}")
    else:
        print("등록했지만 검사를 통과하지 못했습니다:", template["issues"])
        sys.exit(1)


if __name__ == "__main__":
    main()
