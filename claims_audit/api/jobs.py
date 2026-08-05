"""
Job bodies run by the RQ worker (see worker.py). Kept separate from the
routers so both the API process (which enqueues) and the worker process
(which executes) can import the same function by name — required for RQ
to serialize/deserialize the job correctly.
"""
import os
import tempfile
from datetime import datetime

from api.db import SessionLocal
from api.models import GeneratedReport, ClaimRow, Flag
from api.storage import save_file


def run_upload_ingest_job(source_file_id: str, session_id: str, filename: str, tmp_path: str, sheet: str):
    """Runs the actual streaming parse/merge (api/ingest_common.py) off the
    request thread, for both manual upload and link-sync. Always cleans up
    the temp file on disk, success or failure, so large uploads don't pile
    up in /tmp."""
    import os
    from api.ingest_common import parse_and_merge_from_path

    db = SessionLocal()
    try:
        parse_and_merge_from_path(session_id, source_file_id, filename, tmp_path, sheet, db)
    finally:
        db.close()
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def run_graph_sync_job(session_id: str, drive_id: str, folder_path: str):
    """Runs the app-only Graph API delta sync (ingestion path 1 of 3) as a
    background job. Import is deferred so the API process doesn't need the
    sync/ module's dependencies unless a sync is actually enqueued."""
    from sync.ingest import sync_audit_session
    from sync.graph_client import GraphClient
    from api.session_store import SqlAlchemySessionStore

    db = SessionLocal()
    try:
        graph = GraphClient()
        store = SqlAlchemySessionStore(db)
        sync_audit_session(store, graph, session_id, drive_id, folder_path)
    finally:
        db.close()


def run_delegated_graph_sync_job(session_id: str, user_id: str, folder_path: str):
    """Ingestion path 2 of 3: delegated OAuth sync, run as a background job.
    Refreshes the stored token if needed, then drives the same
    sync_audit_session orchestration used by the app-only path (path 1),
    via DelegatedGraphClient's drive-agnostic adapter."""
    from sync.ingest import sync_audit_session
    from sync.ms_oauth import DelegatedGraphClient
    from api.routers.ms_oauth import get_valid_access_token
    from api.session_store import SqlAlchemySessionStore

    db = SessionLocal()
    try:
        access_token = get_valid_access_token(db, user_id)
        client = DelegatedGraphClient(access_token)
        store = SqlAlchemySessionStore(db)
        sync_audit_session(store, client, session_id, "me", folder_path)
    finally:
        db.close()


def generate_report_job(report_id: str, session_id: str, report_type: str):
    db = SessionLocal()
    try:
        report = db.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()
        if not report:
            return
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

            key = f"{session_id}/{report_id}.{report_type}"
            storage_key = save_file(path, key)

        report.object_storage_key = storage_key
        report.status = "ready"
        report.ready_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        report = db.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()
        if report:
            report.status = "error"
            db.commit()
        raise
    finally:
        db.close()


def _compute_kpis(db, session_id, flags):
    total_rows = db.query(ClaimRow).filter(ClaimRow.audit_session_id == session_id).count()
    return {
        "Total Rows": total_rows,
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
