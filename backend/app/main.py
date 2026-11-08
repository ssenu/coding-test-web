"""FastAPI 앱 생성. 실행: uvicorn app.main:create_app --factory --workers 1"""
from fastapi import FastAPI

from app.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    app = FastAPI(title="coding-test-web")
    app.state.settings = settings

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app
