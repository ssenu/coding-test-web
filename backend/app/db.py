"""DB 엔진 생성과 테이블 준비."""
from sqlalchemy import Engine, event
from sqlmodel import SQLModel, create_engine

from app import models  # noqa: F401  (테이블을 metadata에 등록)
from app.config import Settings


def make_engine(settings: Settings) -> Engine:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
