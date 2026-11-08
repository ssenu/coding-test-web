"""FastAPI 앱 생성. 실행: uvicorn app.main:create_app --factory --workers 1"""
from fastapi import FastAPI

from app.api import admin, participant, runs, templates
from app.config import Settings, load_settings
from app.db import init_db, make_engine
from app.ratelimit import RateLimiter
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

    for module in (admin, templates, runs, participant):
        app.include_router(module.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app
