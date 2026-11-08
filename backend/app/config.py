"""환경변수에서 읽는 설정."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    admin_password: str
    secret_key: str
    data_dir: Path
    cookie_secure: bool = False
    web_dist: Path | None = None
    allowed_origins: tuple[str, ...] = ()

    @property
    def db_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"


def load_settings() -> Settings:
    password = os.environ.get("ADMIN_PASSWORD")
    secret = os.environ.get("SECRET_KEY")
    if not password or not secret:
        raise RuntimeError("ADMIN_PASSWORD와 SECRET_KEY 환경변수가 필요합니다.")
    return Settings(
        admin_password=password,
        secret_key=secret,
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        cookie_secure=os.environ.get("COOKIE_SECURE", "0") == "1",
        web_dist=Path(os.environ["WEB_DIST"]) if os.environ.get("WEB_DIST") else None,
        allowed_origins=tuple(
            o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()
        ),
    )
