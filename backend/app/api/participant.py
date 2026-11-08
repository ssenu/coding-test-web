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
