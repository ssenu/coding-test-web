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
            await websocket.accept()
            await websocket.close(code=4404)
            return
        if token:
            token_hash = hash_token(token)
            p = session.exec(
                select(Participant).where(Participant.run_id == run_id, Participant.token_hash == token_hash)
            ).first()
            if p is None:
                await websocket.accept()
                await websocket.close(code=4401)
                return
            participant_id = p.id
        elif not check_admin_cookie(settings, websocket.cookies.get(ADMIN_COOKIE)):
            await websocket.accept()
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
