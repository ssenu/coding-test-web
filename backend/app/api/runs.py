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
