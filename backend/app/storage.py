"""첨부 파일 저장. DB에는 files_dir 기준 상대 경로를 둔다."""
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


def safe_name(name: str | None) -> str:
    base = Path(name or "").name.strip() or "file"
    return base[:120]


def stored_path(files_dir: Path, rel: str) -> Path:
    return files_dir / rel


async def save_upload(
    files_dir: Path, subdir: str, upload: UploadFile, max_bytes: int = MAX_ATTACHMENT_BYTES
) -> tuple[str, int]:
    rel = Path(subdir) / f"{uuid.uuid4().hex}_{safe_name(upload.filename)}"
    target = files_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    too_big = False
    with target.open("wb") as out:
        while chunk := await upload.read(CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                too_big = True
                break
            out.write(chunk)
    if too_big:
        target.unlink(missing_ok=True)
        raise HTTPException(413, "첨부 파일은 10MB까지 올릴 수 있습니다.")
    return rel.as_posix(), size


def copy_stored(files_dir: Path, rel: str, subdir: str) -> str:
    source = files_dir / rel
    original = source.name.split("_", 1)[-1]
    new_rel = Path(subdir) / f"{uuid.uuid4().hex}_{original}"
    (files_dir / new_rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, files_dir / new_rel)
    return new_rel.as_posix()


def delete_stored(files_dir: Path, rel: str) -> None:
    (files_dir / rel).unlink(missing_ok=True)
