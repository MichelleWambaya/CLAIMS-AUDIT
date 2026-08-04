import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import AuditSession, SourceFile, User
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
def trigger_sync(session_id: str, body: SyncRequest, background_tasks: BackgroundTasks,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Kicks off a OneDrive/SharePoint delta sync for this session. In
    production this enqueues a job onto the background worker queue
    (RQ/Celery) rather than FastAPI's BackgroundTasks, which doesn't
    survive a process restart — swap the call below for `queue.enqueue(...)`
    once the queue is wired up; the ingest.sync_audit_session function
    itself doesn't change either way.
    """
    session = db.query(AuditSession).filter(AuditSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from sync.ingest import sync_audit_session
    from sync.graph_client import GraphClient
    from api.session_store import SqlAlchemySessionStore  # adapter implementing sync.ingest.SessionStore

    graph = GraphClient()
    store = SqlAlchemySessionStore(db)
    background_tasks.add_task(
        sync_audit_session, store, graph, session_id, body.drive_id, body.folder_path
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
        }
        for f in files
    ]
