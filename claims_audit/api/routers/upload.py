"""
Manual file upload — no Microsoft permissions needed.

Streams the incoming file to a temp path on disk in bounded chunks
(never calls `.read()` for the whole file at once), then either:
  - returns the workbook's sheet names for the user to pick one (multi-sheet
    Excel only — cheap, doesn't require parsing row data), or
  - creates the SourceFile row and enqueues the actual parse as a
    background job, returning immediately with a status the client can
    poll via GET /sessions/{id}/source-files.

This is what makes "hundreds of MB, multi-million rows" survivable: the
HTTP request only ever does a bounded-memory disk write, never a full
in-memory parse.
"""
import os
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.models import User, SourceFile
from api.queue import default_queue
from api.jobs import run_upload_ingest_job
from api.ingest_common import sniff_excel_sheets
from auth.security import get_current_user

router = APIRouter(prefix="/sessions/{session_id}/upload", tags=["upload"])

_CHUNK_SIZE = 1024 * 1024  # 1 MiB — bounds memory regardless of file size


async def _stream_to_temp_file(upload: UploadFile) -> str:
    os.makedirs(settings.UPLOAD_TMP_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="claims_upload_", suffix=os.path.splitext(upload.filename)[1], dir=settings.UPLOAD_TMP_DIR
    )
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await upload.read(_CHUNK_SIZE)
                if not chunk:
                    break
                out.write(chunk)
    except Exception:
        os.remove(tmp_path)
        raise
    return tmp_path


@router.post("")
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    sheet: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filename = file.filename
    is_excel = filename.lower().endswith((".xlsx", ".xlsm", ".xls"))

    tmp_path = await _stream_to_temp_file(file)

    if is_excel and sheet is None:
        sheet_names = sniff_excel_sheets(tmp_path)
        if len(sheet_names) > 1:
            os.remove(tmp_path)  # cheap re-upload on the next call, keeps this endpoint stateless
            return {"needs_sheet_selection": True, "sheets": sheet_names}
        sheet = sheet_names[0] if sheet_names else None
        if sheet is None:
            os.remove(tmp_path)
            raise HTTPException(status_code=422, detail="Workbook has no sheets.")

    source_file = SourceFile(
        id=uuid.uuid4(),
        audit_session_id=session_id,
        source_type="manual_upload",
        source_ref=filename,
        file_name=filename,
        sheet_name=sheet,
        status="pending",
    )
    db.add(source_file)
    db.commit()

    default_queue.enqueue(
        run_upload_ingest_job, str(source_file.id), session_id, filename, tmp_path, sheet,
        job_timeout="2h",
    )

    return {"source_file_id": str(source_file.id), "status": "queued"}
