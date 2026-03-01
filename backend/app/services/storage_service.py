from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from ..config import settings

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def ensure_directories() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)


def _safe_name(filename: str) -> str:
    return "".join(ch for ch in filename if ch.isalnum() or ch in {"-", "_", "."})


def save_upload(upload: UploadFile, engagement_id: str, entity_id: str | None = None) -> tuple[Path, str]:
    ensure_directories()

    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {suffix}",
        )

    folder = settings.uploads_dir / engagement_id
    if entity_id:
        folder = folder / entity_id
    folder.mkdir(parents=True, exist_ok=True)

    target = folder / f"{uuid4()}_{_safe_name(upload.filename or 'upload') }"

    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_upload_size_mb * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds {settings.max_upload_size_mb}MB",
                )
            digest.update(chunk)
            out.write(chunk)

    return target, digest.hexdigest()
