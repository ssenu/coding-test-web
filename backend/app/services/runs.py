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
