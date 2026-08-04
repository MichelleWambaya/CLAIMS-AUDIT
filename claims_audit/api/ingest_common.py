"""
Shared ingestion logic — extracted from api/routers/upload.py so that
manual upload and link-based sync (api/routers/link_sync.py) run through
the exact same parse/map/merge path, rather than two copies that could
silently drift apart.
"""
import csv
import io
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from api.models import SourceFile, ClaimRow
from rules.column_mapping import map_headers, DEFAULT_ALIASES
from sync.streaming_parser import list_workbook_sheets, stream_excel_rows

CLAIM_LEVEL_REQUIRED = ["member_id", "policy_number", "claim_code"]
ITEM_LEVEL_REQUIRED = ["member_id", "product_name", "visit_date", "item_status"]


def detect_extract_type(mapped_fields_present: set) -> str:
    if {"product_name", "visit_date", "item_status"} & mapped_fields_present:
        return "item_level"
    return "claim_level"


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, (date, datetime)):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def parse_and_merge(
    session_id: str,
    filename: str,
    contents: bytes,
    sheet: Optional[str],
    source_type: str,
    source_ref: str,
    db: Session,
) -> dict:
    """
    Parses raw file bytes (CSV or Excel), maps columns, validates
    required fields, and merges into claim_rows for the given session.
    Returns a dict describing the outcome — never raises for ordinary
    "bad data" cases, only for genuine bugs, so callers can show the
    schema_issues/error info to the user instead of a stack trace.
    """
    is_excel = filename.lower().endswith((".xlsx", ".xlsm", ".xls"))

    if is_excel:
        sheet_names = list_workbook_sheets(io.BytesIO(contents))
        if sheet is None:
            if len(sheet_names) > 1:
                return {"needs_sheet_selection": True, "sheets": sheet_names}
            sheet = sheet_names[0]

        rows_iter, issues = stream_excel_rows(io.BytesIO(contents), sheet)
        if issues:
            return {"error": True, "schema_issues": [i.to_dict() for i in issues]}
        raw_rows = list(rows_iter)
    else:
        text = contents.decode("utf-8", errors="replace")
        raw_rows = list(csv.DictReader(io.StringIO(text)))

    if not raw_rows:
        return {"error": True, "schema_issues": [{"kind": "empty_file", "detail": "No data rows found."}]}

    headers = list(raw_rows[0].keys())
    mapped = map_headers(headers, DEFAULT_ALIASES)
    present_fields = set(v for v in mapped.values() if v)
    extract_type = detect_extract_type(present_fields)
    required = ITEM_LEVEL_REQUIRED if extract_type == "item_level" else CLAIM_LEVEL_REQUIRED
    missing = [f for f in required if f not in present_fields]
    if missing:
        return {
            "error": True,
            "schema_issues": [{
                "kind": "missing_column",
                "detail": f"Missing required field(s) for a {extract_type} extract: {', '.join(missing)}",
            }],
        }

    source_file = SourceFile(
        id=uuid.uuid4(),
        audit_session_id=session_id,
        source_type=source_type,
        source_ref=source_ref,
        file_name=filename,
        sheet_name=sheet,
        extract_type=extract_type,
        status="parsing",
    )
    db.add(source_file)
    db.commit()

    has_item_status_col = "item_status" in mapped.values()
    claim_row_objs = []
    for i, raw_row in enumerate(raw_rows):
        row = {}
        for raw_key, value in raw_row.items():
            canonical = mapped.get(raw_key)
            if canonical:
                row[canonical] = value

        claim_row_objs.append(ClaimRow(
            audit_session_id=session_id,
            source_file_id=source_file.id,
            source_row_number=i,
            member_id=row.get("member_id"),
            policy_number=row.get("policy_number"),
            claim_code=row.get("claim_code"),
            payer=row.get("payer"),
            category=row.get("category"),
            plan=row.get("plan"),
            claim_date=parse_date(row.get("claim_date")),
            diagnosis_type=row.get("diagnosis_type"),
            diagnosis_name=row.get("diagnosis_name"),
            invoice_number=row.get("invoice_number"),
            amount=row.get("amount") or None,
            provider=row.get("provider"),
            product_name=row.get("product_name"),
            visit_date=parse_date(row.get("visit_date")),
            item_status=row.get("item_status"),
            has_item_status_column=has_item_status_col,
            raw_extra={},
        ))

    db.bulk_save_objects(claim_row_objs)
    source_file.status = "merged"
    source_file.row_count = len(claim_row_objs)
    source_file.ingested_at = datetime.utcnow()
    db.commit()

    return {
        "source_file_id": str(source_file.id),
        "extract_type": extract_type,
        "rows_merged": len(claim_row_objs),
    }
