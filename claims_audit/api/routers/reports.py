import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import GeneratedReport, User
from api.queue import default_queue
from api.storage import retrieve_path
from api.jobs import generate_report_job
from auth.security import get_current_user

router = APIRouter(prefix="/sessions/{session_id}/reports", tags=["reports"])

_MEDIA_TYPES = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class GenerateReportRequest(BaseModel):
    report_type: str  # 'pptx' | 'pdf' | 'xlsx'
    saved_view_id: Optional[str] = None


@router.post("")
def request_report(session_id: str, body: GenerateReportRequest,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.report_type not in ("pptx", "pdf", "xlsx"):
        raise HTTPException(status_code=400, detail="report_type must be pptx, pdf, or xlsx")

    report = GeneratedReport(
        id=uuid.uuid4(),
        audit_session_id=session_id,
        saved_view_id=body.saved_view_id,
        generated_by=user.id,
        report_type=body.report_type,
        object_storage_key="",  # filled in once generation completes
        status="queued",
    )
    db.add(report)
    db.commit()

    # Real background job via RQ/Redis — survives process restarts and
    # doesn't block the request thread, unlike FastAPI BackgroundTasks.
    default_queue.enqueue(
        generate_report_job, str(report.id), session_id, body.report_type,
        job_timeout="30m",
    )

    return {"id": str(report.id), "status": "queued"}


@router.get("")
def list_reports(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Past reports remain browsable — not a one-time download link."""
    reports = (
        db.query(GeneratedReport)
        .filter(GeneratedReport.audit_session_id == session_id)
        .order_by(GeneratedReport.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(r.id), "report_type": r.report_type, "status": r.status,
            "created_at": r.created_at.isoformat(),
            "ready_at": r.ready_at.isoformat() if r.ready_at else None,
            "download_url": f"/sessions/{session_id}/reports/{r.id}/download" if r.status == "ready" else None,
        }
        for r in reports
    ]


@router.get("/{report_id}")
def get_report_status(session_id: str, report_id: str, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    report = db.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "id": str(report.id), "status": report.status, "report_type": report.report_type,
        "download_url": f"/sessions/{session_id}/reports/{report.id}/download" if report.status == "ready" else None,
    }


@router.get("/{report_id}/download")
def download_report(session_id: str, report_id: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    report = db.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != "ready":
        raise HTTPException(status_code=409, detail=f"Report is not ready yet (status: {report.status})")
    local_path = retrieve_path(report.object_storage_key)
    filename = f"report_{report_id}.{report.report_type}"
    return FileResponse(local_path, media_type=_MEDIA_TYPES[report.report_type], filename=filename)
