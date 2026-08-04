"""SQLAlchemy models mirroring db/schema.sql exactly — this is the ORM
layer the API routers use; the .sql file remains the source of truth for
anyone provisioning the DB directly (e.g. via a migration tool)."""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, ForeignKey, Numeric, BigInteger,
    Date, Integer, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 'analyst' | 'admin'
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditSession(Base):
    __tablename__ = "audit_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    delta_link = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class SourceFile(Base):
    __tablename__ = "source_files"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_session_id = Column(UUID(as_uuid=True), ForeignKey("audit_sessions.id"), nullable=False)
    source_type = Column(String, nullable=False)  # 'onedrive' | 'sharepoint' | 'manual_upload'
    source_ref = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    sheet_name = Column(String, nullable=True)
    extract_type = Column(String, nullable=True)
    row_count = Column(BigInteger, nullable=True)
    status = Column(String, nullable=False, default="pending")
    schema_issues = Column(JSONB, nullable=True)
    ingested_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ClaimRow(Base):
    __tablename__ = "claim_rows"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    audit_session_id = Column(UUID(as_uuid=True), ForeignKey("audit_sessions.id"), nullable=False)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey("source_files.id"), nullable=False)
    source_row_number = Column(Integer, nullable=False)
    member_id = Column(String)
    policy_number = Column(String)
    claim_code = Column(String)
    payer = Column(String)
    category = Column(String)
    plan = Column(String)
    claim_date = Column(Date)
    diagnosis_type = Column(String)
    diagnosis_name = Column(String)
    invoice_number = Column(String)
    amount = Column(Numeric(14, 2))
    provider = Column(String)
    product_name = Column(String)
    visit_date = Column(Date)
    item_status = Column(String)
    has_item_status_column = Column(Boolean, default=True)
    raw_extra = Column(JSONB)


class Flag(Base):
    __tablename__ = "flags"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    audit_session_id = Column(UUID(as_uuid=True), ForeignKey("audit_sessions.id"), nullable=False)
    flag_type = Column(String, nullable=False)
    group_id = Column(String, nullable=True)
    detail = Column(JSONB, nullable=False)
    computed_at = Column(DateTime, default=datetime.utcnow)


class FlagReview(Base):
    __tablename__ = "flag_reviews"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    flag_id = Column(BigInteger, ForeignKey("flags.id"), nullable=False)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False)  # confirmed | false_positive | needs_follow_up
    note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, default=datetime.utcnow)


class FlagOverride(Base):
    __tablename__ = "flag_overrides"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    flag_id = Column(BigInteger, ForeignKey("flags.id"), nullable=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    justification = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SavedView(Base):
    __tablename__ = "saved_views"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_session_id = Column(UUID(as_uuid=True), ForeignKey("audit_sessions.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    view_config_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class GeneratedReport(Base):
    __tablename__ = "generated_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_session_id = Column(UUID(as_uuid=True), ForeignKey("audit_sessions.id"), nullable=False)
    saved_view_id = Column(UUID(as_uuid=True), ForeignKey("saved_views.id"), nullable=True)
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    report_type = Column(String, nullable=False)  # pptx | pdf | xlsx
    object_storage_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    created_at = Column(DateTime, default=datetime.utcnow)
    ready_at = Column(DateTime, nullable=True)


class RuleConfigRow(Base):
    __tablename__ = "rule_config"
    audit_session_id = Column(UUID(as_uuid=True), ForeignKey("audit_sessions.id"), primary_key=True)
    config_json = Column(JSONB, nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class AccessLog(Base):
    __tablename__ = "access_log"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    resource_ref = Column(String, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow)
