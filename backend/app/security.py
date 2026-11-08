"""배포용 보안 설정: 출처 확인, 요청 크기 제한, 보안 헤더, 로그의 토큰 가리기."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MAX_BODY_BYTES = 12 * 1024 * 1024  # 첨부 파일 10MB + 여유
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
WS_FORBIDDEN_ORIGIN = 4403

# Vue Flow와 CodeMirror가 인라인 스타일을 쓰므로 style-src에만 'unsafe-inline'을 허용한다
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}


def origin_allowed(allowed: tuple[str, ...], origin: str | None) -> bool:
    """허용 목록이 비어 있으면(개발) 검사하지 않는다. Origin 헤더가 없는 요청도 통과시킨다."""
    if not allowed or origin is None:
        return True
    return origin.rstrip("/") in allowed


def install_security(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        allowed = request.app.state.settings.allowed_origins
        if request.method in UNSAFE_METHODS and not origin_allowed(allowed, request.headers.get("origin")):
            response = JSONResponse({"detail": "허용되지 않은 출처입니다."}, status_code=403)
        elif int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
            response = JSONResponse({"detail": "요청이 너무 큽니다."}, status_code=413)
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


class RedactTokenFilter(logging.Filter):
    """접속 로그에 찍히는 주소에서 참가자 토큰(?token=...)을 지운다."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                a.split("?", 1)[0] if isinstance(a, str) and "token=" in a else a for a in record.args
            )
        return True


def install_log_redaction() -> None:
    for name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactTokenFilter) for f in logger.filters):
            logger.addFilter(RedactTokenFilter())
