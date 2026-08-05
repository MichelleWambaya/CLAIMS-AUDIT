import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.models import AuditSession, SourceFile, User
from api.queue import default_queue
from auth.security import get_current_user

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    name: str


class SyncRequest(BaseModel):
    drive_id: str
    folder_path: str


@router.post("")
def create_session(body: CreateSessionRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    session = AuditSession(id=uuid.uuid4(), name=body.name, created_by=user.id)
    db.add(session)
    db.commit()
    return {"id": str(session.id), "name": session.name}


@router.get("")
def list_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sessions = db.query(AuditSession).order_by(AuditSession.created_at.desc()).all()
    return [{"id": str(s.id), "name": s.name, "created_at": s.created_at.isoformat()} for s in sessions]


@router.post("/{session_id}/sync")
def trigger_sync(session_id: str, body: SyncRequest,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Kicks off a OneDrive/SharePoint delta sync for this session using the
    app-only Graph connector (ingestion path 1 of 3 — see also
    /link-sync for the share-link path and /ms-oauth for delegated OAuth).
    Runs as a real RQ background job so it survives a process restart and
    doesn't block this request for a large folder.
    """
    session = db.query(AuditSession).filter(AuditSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not settings.graph_app_only_configured():
        raise HTTPException(
            status_code=503,
            detail="The app-only OneDrive/SharePoint connector isn't configured on this deployment "
                   "(missing MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET). Use manual upload, the "
                   "share-link sync, or ask an admin to register an Azure AD app and set those "
                   "environment variables.",
        )

    from api.jobs import run_graph_sync_job
    default_queue.enqueue(
        run_graph_sync_job, session_id, body.drive_id, body.folder_path,
        job_timeout="2h",
    )
    return {"status": "sync_started"}


@router.get("/{session_id}/source-files")
def list_source_files(session_id: str, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    files = db.query(SourceFile).filter(SourceFile.audit_session_id == session_id).all()
    return [
        {
            "id": str(f.id),
            "file_name": f.file_name,
            "status": f.status,
            "row_count": f.row_count,
            "schema_issues": f.schema_issues,
            "extract_type": f.extract_type,
            "source_type": f.source_type,
        }
        for f in files
    ]
