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
