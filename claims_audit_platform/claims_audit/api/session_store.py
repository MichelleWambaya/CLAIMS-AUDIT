"""
Concrete storage adapter for sync.ingest.SessionStore, backed by the
SQLAlchemy models in api/models.py. Kept separate from the ingest module
itself so the ingest logic stays testable against a fake/in-memory store.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from api.models import AuditSession, SourceFile, ClaimRow
from sync.graph_client import DriveItem


class SqlAlchemySessionStore:
    def __init__(self, db: Session):
        self.db = db
        self._progress_cache: dict[str, int] = {}

    def create_source_file(self, audit_session_id: str, drive_item: DriveItem, extract_type: Optional[str]) -> str:
        sf = SourceFile(
            id=uuid.uuid4(),
            audit_session_id=audit_session_id,
            source_type="onedrive",
            source_ref=drive_item.id,
            file_name=drive_item.name,
            extract_type=extract_type,
            status="pending",
        )
        self.db.add(sf)
        self.db.commit()
        return str(sf.id)

    def update_source_file_status(self, source_file_id: str, status: str, schema_issues: Optional[list] = None):
        sf = self.db.query(SourceFile).filter(SourceFile.id == source_file_id).first()
        if not sf:
            return
        sf.status = status
        if schema_issues is not None:
            sf.schema_issues = schema_issues
        if status == "merged":
            sf.ingested_at = datetime.utcnow()
            sf.row_count = self._progress_cache.get(source_file_id)
        self.db.commit()

    def insert_claim_rows_batch(self, audit_session_id: str, source_file_id: str, rows: list):
        objs = []
        for i, r in enumerate(rows):
            objs.append(ClaimRow(
                audit_session_id=audit_session_id,
                source_file_id=source_file_id,
                source_row_number=i,
                member_id=r.get("member_id"),
                policy_number=r.get("policy_number"),
                claim_code=r.get("claim_code"),
                payer=r.get("payer"),
                category=r.get("category"),
                plan=r.get("plan"),
                claim_date=r.get("claim_date"),
                diagnosis_type=r.get("diagnosis_type"),
                diagnosis_name=r.get("diagnosis_name"),
                invoice_number=r.get("invoice_number"),
                amount=r.get("amount"),
                provider=r.get("provider"),
                product_name=r.get("product_name"),
                visit_date=r.get("visit_date"),
                item_status=r.get("item_status"),
                has_item_status_column=r.get("_has_item_status_column", True),
                raw_extra=r.get("raw_extra", {}),
            ))
        self.db.bulk_save_objects(objs)
        self.db.commit()

    def save_delta_link(self, audit_session_id: str, delta_link: str):
        session = self.db.query(AuditSession).filter(AuditSession.id == audit_session_id).first()
        if session:
            session.delta_link = delta_link
            session.updated_at = datetime.utcnow()
            self.db.commit()

    def get_delta_link(self, audit_session_id: str) -> Optional[str]:
        session = self.db.query(AuditSession).filter(AuditSession.id == audit_session_id).first()
        return session.delta_link if session else None

    def report_progress(self, source_file_id: str, rows_processed: int, rows_total: Optional[int]):
        self._progress_cache[source_file_id] = rows_processed
        # In production, push this over a websocket / write to a
        # `sync_progress` cache (e.g. Redis) the frontend polls, per §4's
        # "1.2M / 4.5M rows processed" requirement.
