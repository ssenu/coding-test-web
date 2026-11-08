"""관리자 로그인 API."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.auth import ADMIN_COOKIE, ADMIN_MAX_AGE, make_admin_cookie, password_ok
from app.deps import SettingsDep, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, settings: SettingsDep) -> dict:
    client_key = request.client.host if request.client else "unknown"
    if not request.app.state.login_limiter.allow(client_key):
        raise HTTPException(429, "로그인 시도가 너무 많습니다. 잠시 뒤 다시 시도하세요.")
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
