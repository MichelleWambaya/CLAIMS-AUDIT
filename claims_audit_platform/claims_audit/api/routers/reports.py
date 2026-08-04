import os
import uuid
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db, OBJECT_STORAGE_BUCKET
from api.models import GeneratedReport, ClaimRow, Flag, User
from auth.security import get_current_user

router = APIRouter(prefix="/sessions/{session_id}/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    report_type: str  # 'pptx' | 'pdf' | 'xlsx'
    saved_view_id: Optional[str] = None


@router.post("")
def request_report(session_id: str, body: GenerateReportRequest, background_tasks: BackgroundTasks,
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

    # Background job, per §7: "Exports should be generated as background
    # jobs for large datasets, with a notification/download-ready state."
    # Swap for a real queue (RQ/Celery) in production — BackgroundTasks
    # doesn't survive a process restart.
    background_tasks.add_task(_generate_report_job, str(report.id), session_id, body.report_type)

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
            "download_key": r.object_storage_key or None,
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
        "download_key": report.object_storage_key or None,
    }


def _generate_report_job(report_id: str, session_id: str, report_type: str):
    """
    Runs off the request thread. Pulls session data, builds the requested
    file with reports/{pptx,pdf,xlsx}_generator.py, uploads to object
    storage, and flips status to ready — or 'error' on failure, never
    leaving a report stuck at 'generating'.
    """
    from api.db import SessionLocal
    db = SessionLocal()
    try:
        report = db.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()
        report.status = "generating"
        db.commit()

        flags = db.query(Flag).filter(Flag.audit_session_id == session_id).all()
        kpis = _compute_kpis(db, session_id, flags)

        with tempfile.TemporaryDirectory() as tmp_dir:
            if report_type == "pptx":
                from reports.pptx_generator import build_presentation
                path = os.path.join(tmp_dir, "report.pptx")
                build_presentation(
                    session_name=session_id, kpis=kpis,
                    top_categories=_top_categories(db, session_id),
                    priority_flags=_priority_flags(flags),
                    recommendations=_recommendations(flags),
                    output_path=path,
                )
            elif report_type == "pdf":
                from reports.pdf_generator import presentation_view_to_pdf
                path = presentation_view_to_pdf(
                    session_name=session_id, kpis=kpis,
                    top_categories=_top_categories(db, session_id),
                    priority_flags=_priority_flags(flags),
                    recommendations=_recommendations(flags),
                    output_dir=tmp_dir,
                )
            else:  # xlsx
                from reports.xlsx_generator import build_workbook
                path = os.path.join(tmp_dir, "report.xlsx")
                build_workbook(session_id, _flag_detail_rows(flags), path)

            storage_key = _upload_to_object_storage(path, session_id, report_id, report_type)

        report.object_storage_key = storage_key
        report.status = "ready"
        from datetime import datetime
        report.ready_at = datetime.utcnow()
        db.commit()
    except Exception:
        report = db.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()
        if report:
            report.status = "error"
            db.commit()
    finally:
        db.close()


def _compute_kpis(db, session_id, flags):
    total_amount = db.query(ClaimRow).filter(ClaimRow.audit_session_id == session_id).count()
    return {
        "Total Rows": total_amount,
        "Total Flags": len(flags),
        "Flag Types": len(set(f.flag_type for f in flags)),
    }


def _top_categories(db, session_id):
    from sqlalchemy import func
    rows = (
        db.query(ClaimRow.category, func.sum(ClaimRow.amount), func.count())
        .filter(ClaimRow.audit_session_id == session_id, ClaimRow.category.isnot(None))
        .group_by(ClaimRow.category)
        .order_by(func.sum(ClaimRow.amount).desc())
        .limit(8)
        .all()
    )
    return [{"category": c, "amount": float(amt or 0), "flag_count": cnt} for c, amt, cnt in rows]


def _priority_flags(flags):
    return [
        {"flag_type": f.flag_type, "detail_summary": str(f.detail)[:80], "amount_or_score": ""}
        for f in flags[:6]
    ]


def _recommendations(flags):
    recs = []
    types_present = set(f.flag_type for f in flags)
    if "pricing_anomaly" in types_present:
        recs.append("Review high-value outlier claims flagged by the IQR pricing check.")
    if "item_duplicate" in types_present or "claim_duplicate" in types_present:
        recs.append("Investigate duplicate clusters for potential double-billing.")
    if "non_payable" in types_present:
        recs.append("Confirm non-payable category matches, using the override path for legitimate exceptions.")
    if not recs:
        recs.append("No high-priority patterns detected in this batch.")
    return recs


def _flag_detail_rows(flags):
    out = []
    for f in flags:
        d = f.detail or {}
        out.append({
            "row_id": f.id,
            "flag_type": f.flag_type,
            "member_id": d.get("member_id"),
            "category": d.get("category"),
            "product_or_diagnosis": d.get("matched_keyword") or d.get("products"),
            "amount": d.get("amount"),
            "flag_reason": d.get("reason") or f.flag_type,
            "duplicate_group_id": f.group_id,
            "days_from_first_visit": d.get("days_from_first_visit"),
            "similarity_score": d.get("similarity_scores"),
            "review_status": "",
        })
    return out


def _upload_to_object_storage(local_path: str, session_id: str, report_id: str, report_type: str) -> str:
    """
    Stub for the real S3-compatible upload. Swap for boto3 put_object
    against OBJECT_STORAGE_BUCKET once infra credentials are wired up —
    the rest of this router only depends on getting a stable key back.
    """
    key = f"{OBJECT_STORAGE_BUCKET}/{session_id}/{report_id}.{report_type}"
    # e.g.: s3_client.upload_file(local_path, OBJECT_STORAGE_BUCKET, key)
    return key
