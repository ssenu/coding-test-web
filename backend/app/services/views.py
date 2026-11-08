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
