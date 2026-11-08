"""시험장(템플릿) 관리 API. 관리자 전용."""
import copy

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.deps import SessionDep, SettingsDep, require_admin
from app.engine.graph import GraphError, Issue, parse_graph, validate_graph
from app.models import Run, Template, TemplateFile, empty_graph, iso, utcnow
from app.storage import copy_stored, delete_stored, safe_name, save_upload, stored_path

router = APIRouter(
    prefix="/api/templates", tags=["templates"], dependencies=[Depends(require_admin)]
)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    graph: dict = Field(default_factory=empty_graph)


def check_graph(data: dict) -> list[Issue]:
    try:
        graph = parse_graph(data)
    except GraphError as exc:
        return [Issue(str(exc))]
    return validate_graph(graph)


def template_out(t: Template) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "graph": t.graph,
        "valid": t.valid,
        "issues": [{"message": i.message, "box_ids": list(i.box_ids)} for i in check_graph(t.graph)],
        "updated_at": iso(t.updated_at),
    }


def file_out(f: TemplateFile) -> dict:
    return {"id": f.id, "box_id": f.box_id, "filename": f.filename, "size": f.size}


def get_template(session: Session, template_id: int) -> Template:
    template = session.get(Template, template_id)
    if template is None:
        raise HTTPException(404, "시험장을 찾을 수 없습니다.")
    return template


def template_files(session: Session, template_id: int) -> list[TemplateFile]:
    return list(
        session.exec(
            select(TemplateFile).where(TemplateFile.template_id == template_id).order_by(col(TemplateFile.id))
        ).all()
    )


@router.get("")
def list_templates(session: SessionDep) -> list[dict]:
    rows = session.exec(select(Template).order_by(col(Template.updated_at).desc())).all()
    return [
        {"id": t.id, "name": t.name, "description": t.description, "valid": t.valid, "updated_at": iso(t.updated_at)}
        for t in rows
    ]


@router.post("", status_code=201)
def create_template(body: TemplateIn, session: SessionDep) -> dict:
    template = Template(
        name=body.name,
        description=body.description,
        graph=body.graph,
        valid=not check_graph(body.graph),
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    return template_out(template)


@router.get("/{template_id}")
def read_template(template_id: int, session: SessionDep) -> dict:
    return template_out(get_template(session, template_id))


@router.put("/{template_id}")
def update_template(template_id: int, body: TemplateIn, session: SessionDep) -> dict:
    template = get_template(session, template_id)
    template.name = body.name
    template.description = body.description
    template.graph = body.graph
    template.valid = not check_graph(body.graph)
    template.updated_at = utcnow()
    session.add(template)
    session.commit()
    session.refresh(template)
    return template_out(template)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, session: SessionDep, settings: SettingsDep) -> Response:
    template = get_template(session, template_id)
    if session.exec(select(Run).where(Run.template_id == template.id)).first() is not None:
        raise HTTPException(409, "회차가 있는 시험장은 삭제할 수 없습니다. 복제해서 새로 만드세요.")
    for f in template_files(session, template.id):
        delete_stored(settings.files_dir, f.stored_path)
        session.delete(f)
    session.flush()
    session.delete(template)
    session.commit()
    return Response(status_code=204)


@router.post("/{template_id}/duplicate", status_code=201)
def duplicate_template(template_id: int, session: SessionDep, settings: SettingsDep) -> dict:
    source = get_template(session, template_id)
    clone = Template(
        name=f"{source.name} 사본",
        description=source.description,
        graph=copy.deepcopy(source.graph),
        valid=source.valid,
    )
    session.add(clone)
    session.flush()
    for f in template_files(session, source.id):
        session.add(
            TemplateFile(
                template_id=clone.id,
                box_id=f.box_id,
                filename=f.filename,
                stored_path=copy_stored(settings.files_dir, f.stored_path, f"templates/{clone.id}"),
                size=f.size,
            )
        )
    session.commit()
    session.refresh(clone)
    return template_out(clone)


@router.get("/{template_id}/files")
def list_files(template_id: int, session: SessionDep) -> list[dict]:
    get_template(session, template_id)
    return [file_out(f) for f in template_files(session, template_id)]


@router.post("/{template_id}/files", status_code=201)
async def upload_file(
    template_id: int,
    session: SessionDep,
    settings: SettingsDep,
    box_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    template = get_template(session, template_id)
    rel, size = await save_upload(settings.files_dir, f"templates/{template.id}", file)
    record = TemplateFile(
        template_id=template.id, box_id=box_id, filename=safe_name(file.filename), stored_path=rel, size=size
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return file_out(record)


def _template_file(session: Session, template_id: int, file_id: int) -> TemplateFile:
    record = session.get(TemplateFile, file_id)
    if record is None or record.template_id != template_id:
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    return record


@router.get("/{template_id}/files/{file_id}")
def download_file(template_id: int, file_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
    record = _template_file(session, template_id, file_id)
    return FileResponse(stored_path(settings.files_dir, record.stored_path), filename=record.filename)


@router.delete("/{template_id}/files/{file_id}", status_code=204)
def delete_file(template_id: int, file_id: int, session: SessionDep, settings: SettingsDep) -> Response:
    record = _template_file(session, template_id, file_id)
    delete_stored(settings.files_dir, record.stored_path)
    session.delete(record)
    session.commit()
    return Response(status_code=204)
