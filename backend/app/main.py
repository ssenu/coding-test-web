"""FastAPI 앱 생성. 실행: uvicorn app.main:create_app --factory --workers 1"""
from fastapi import FastAPI

from app.api import admin, participant, runs, templates, ws
from app.config import Settings, load_settings
from app.db import init_db, make_engine
from app.ratelimit import RateLimiter
from app.security import install_log_redaction, install_security
from app.web import mount_web
from app.ws.hub import Hub


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings)
    init_db(engine)

    app = FastAPI(title="coding-test-web")
    app.state.settings = settings
    app.state.engine = engine
    app.state.hub = Hub()
    app.state.join_limiter = RateLimiter(limit=10, window_seconds=60)
    app.state.login_limiter = RateLimiter(limit=5, window_seconds=60)
    install_security(app)
    install_log_redaction()

    for module in (admin, templates, runs, participant, ws):
        app.include_router(module.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    if settings.web_dist is not None:
        mount_web(app, settings.web_dist)  # 모든 경로를 받으므로 맨 마지막에

    return app
