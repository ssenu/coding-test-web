"""DB 테이블. 시각은 모두 timezone이 붙은 UTC(datetime)로 다룬다. SQLModel 0.0.48+는 naive datetime 저장을 거부한다."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def empty_graph() -> dict:
    return {"boxes": [], "edges": []}


class Template(SQLModel, table=True):
    __tablename__ = "templates"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    graph: dict = Field(default_factory=empty_graph, sa_column=Column(JSON, nullable=False))
    valid: bool = False
    updated_at: datetime = Field(default_factory=utcnow)


class TemplateFile(SQLModel, table=True):
    __tablename__ = "template_files"
    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="templates.id", index=True)
    box_id: str
    filename: str
    stored_path: str
    size: int


class Run(SQLModel, table=True):
    __tablename__ = "runs"
    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="templates.id", index=True)
    name: str
    graph_snapshot: dict = Field(default_factory=empty_graph, sa_column=Column(JSON, nullable=False))
    entry_code: str = Field(index=True, unique=True)
    status: str = "lobby"  # lobby / running / finished
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunFile(SQLModel, table=True):
    __tablename__ = "run_files"
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    filename: str
    stored_path: str
    size: int


class Participant(SQLModel, table=True):
    __tablename__ = "participants"
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    name: str
    token_hash: str = Field(index=True)
    rejoin_token_hash: str | None = Field(default=None, index=True)
    assigned_box_id: str | None = None
    is_leader: bool = False
    joined_at: datetime = Field(default_factory=utcnow)
    last_active_at: datetime | None = None


class BoxState(SQLModel, table=True):
    __tablename__ = "box_states"
    __table_args__ = (UniqueConstraint("run_id", "box_id"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    state: str = "locked"  # locked / open / closed
    opened_at: datetime | None = None
    closed_at: datetime | None = None


class EdgeApproval(SQLModel, table=True):
    __tablename__ = "edge_approvals"
    __table_args__ = (UniqueConstraint("run_id", "edge_id"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    edge_id: str
    approved_at: datetime = Field(default_factory=utcnow)


class Submission(SQLModel, table=True):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("run_id", "box_id"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    participant_id: int = Field(foreign_key="participants.id")
    files: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    submitted_at: datetime = Field(default_factory=utcnow)


class TeamDraft(SQLModel, table=True):
    __tablename__ = "team_drafts"
    __table_args__ = (UniqueConstraint("run_id", "box_id"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    files: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    updated_at: datetime = Field(default_factory=utcnow)


class TeamVersion(SQLModel, table=True):
    __tablename__ = "team_versions"
    __table_args__ = (UniqueConstraint("run_id", "box_id", "version_no"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    box_id: str
    version_no: int
    files: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    saved_at: datetime = Field(default_factory=utcnow)
    is_final: bool = False
