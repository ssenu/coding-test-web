"""진행 동작: 개인 제출, 연결선 승인, 팀 편집. REST API와 웹소켓이 함께 쓴다."""
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
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
    for edge_id in dict.fromkeys(edge_ids):
        edge = graph.edge(edge_id)
        if edge is None or edge.mode != "approval":
            raise HTTPException(404, f"승인 연결선이 아닙니다: {edge_id}")
        if edge_id in fs.approved:
            continue
        if not can_approve(edge, fs.states):
            raise HTTPException(409, f"아직 승인할 수 없는 연결선입니다: {edge_id}")
        edges.append(edge)
    unsubmitted = list(dict.fromkeys(
        e.source for e in edges
        if graph.boxes[e.source].type == "personal" and e.source not in fs.submitted
    ))
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
    try:
        session.commit()
    except IntegrityError:
        # 동시 요청이 먼저 같은 연결선을 승인했다: 이미 반영된 상태이므로 이벤트 없이 진행만 맞춘다.
        session.rollback()
        await advance_run(session, hub, run)
        return
    for edge in edges:
        await hub.to_all(run.id, "edge_approved", {"edge_id": edge.id})
    await advance_run(session, hub, run)
