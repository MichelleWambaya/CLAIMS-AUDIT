"""
Manual file upload — no Microsoft permissions needed. Two-step flow for
multi-sheet Excel files (§4 requires explicit sheet selection):
  1. POST without `sheet` -> if it's a multi-sheet workbook, returns the
     list of sheet names and does nothing else yet.
  2. POST again with `sheet` set -> actually parses and merges.
"""
import io

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional

from api.db import get_db
from api.models import User
from auth.security import get_current_user
from api.ingest_common import parse_and_merge

router = APIRouter(prefix="/sessions/{session_id}/upload", tags=["upload"])


@router.post("")
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    sheet: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contents = await file.read()
    return parse_and_merge(
        session_id=session_id,
        filename=file.filename,
        contents=contents,
        sheet=sheet,
        source_type="manual_upload",
        source_ref=file.filename,
        db=db,
    )
