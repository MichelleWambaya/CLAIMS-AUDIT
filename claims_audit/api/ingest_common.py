"""
Shared ingestion logic used by manual upload, link-sync, and the Graph API
connector — one code path for parse -> column-map -> validate -> merge, so
they can't silently drift apart (build prompt §5.6).

Rewritten for true streaming (build prompt "Handling very large data
volumes"): rows are processed one at a time from the generator produced by
sync/streaming_parser.py and committed in bounded-size batches — this file
never builds a `list()` of every row in memory, and never runs inside the
request/response cycle for anything beyond a first cheap sheet-name check.
"""
import csv
import uuid
from datetime import date, datetime
from typing import Optional, Iterator, Dict, Any

from sqlalchemy.orm import Session

from api.models import SourceFile, ClaimRow
from rules.column_mapping import map_headers, DEFAULT_ALIASES
from sync.streaming_parser import list_workbook_sheets, stream_excel_rows

CLAIM_LEVEL_REQUIRED = ["member_id", "policy_number", "claim_code"]
ITEM_LEVEL_REQUIRED = ["member_id", "product_name", "visit_date", "item_status"]

BATCH_SIZE = 2000  # rows per DB commit — bounds memory regardless of file size


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


def _csv_row_iterator(path: str) -> Iterator[Dict[str, Any]]:
    """True streaming CSV read: csv.DictReader over a file handle never
    holds more than one row (plus its own small internal buffer) at once."""
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def sniff_excel_sheets(path: str) -> list:
    """Cheap sheet-name listing without loading any cell data — safe to
    call synchronously inside a request, unlike the actual row parse."""
    with open(path, "rb") as f:
        return list_workbook_sheets(f)


def parse_and_merge_from_path(
    session_id: str,
    source_file_id: str,
    filename: str,
    path: str,
    sheet: Optional[str],
    db: Session,
) -> dict:
    """
    Streams rows from `path` (already on local disk — the caller is
    responsible for how it got there, whether that's a chunked upload
    write, a `requests.get(stream=True)` download, or a Graph API
    download), maps columns, validates required fields, and merges into
    claim_rows in bounded-size batches.

    Meant to run inside a background job (see api/jobs.py), not inline in
    an HTTP request — this can take minutes for a very large file.
    """
    source_file = db.query(SourceFile).filter(SourceFile.id == source_file_id).first()
    if not source_file:
        raise ValueError(f"SourceFile {source_file_id} not found")

    is_excel = filename.lower().endswith((".xlsx", ".xlsm", ".xls"))

    try:
        if is_excel:
            with open(path, "rb") as f:
                rows_iter, issues = stream_excel_rows(f, sheet)
                if issues:
                    source_file.status = "error"
                    source_file.schema_issues = [i.to_dict() for i in issues]
                    db.commit()
                    return {"error": True, "schema_issues": source_file.schema_issues}
                result = _stream_merge(session_id, source_file, rows_iter, db)
        else:
            rows_iter = _csv_row_iterator(path)
            result = _stream_merge(session_id, source_file, rows_iter, db)
        return result
    except Exception as exc:
        source_file.status = "error"
        source_file.schema_issues = [{"kind": "unexpected_error", "detail": str(exc)}]
        db.commit()
        raise


def _stream_merge(session_id: str, source_file: SourceFile, rows_iter: Iterator[Dict[str, Any]], db: Session) -> dict:
    mapped = None
    present_fields = None
    extract_type = None
    has_item_status_col = False
    batch = []
    total = 0

    for i, raw_row in enumerate(rows_iter):
        if mapped is None:
            # First row establishes the header mapping and required-field
            # check — done once, not per row.
            headers = list(raw_row.keys())
            mapped = map_headers(headers, DEFAULT_ALIASES)
            present_fields = set(v for v in mapped.values() if v)
            extract_type = detect_extract_type(present_fields)
            required = ITEM_LEVEL_REQUIRED if extract_type == "item_level" else CLAIM_LEVEL_REQUIRED
            missing = [f for f in required if f not in present_fields]
            if missing:
                source_file.status = "error"
                source_file.schema_issues = [{
                    "kind": "missing_column",
                    "detail": f"Missing required field(s) for a {extract_type} extract: {', '.join(missing)}",
                }]
                db.commit()
                return {"error": True, "schema_issues": source_file.schema_issues}
            has_item_status_col = "item_status" in mapped.values()
            source_file.extract_type = extract_type
            source_file.status = "parsing"
            db.commit()

        row = {}
        for raw_key, value in raw_row.items():
            canonical = mapped.get(raw_key)
            if canonical:
                row[canonical] = value

        batch.append(ClaimRow(
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
        total += 1

        if len(batch) >= BATCH_SIZE:
            db.bulk_save_objects(batch)
            source_file.row_count = total  # live progress, visible to polling clients
            db.commit()
            batch = []

    if batch:
        db.bulk_save_objects(batch)

    if total == 0:
        source_file.status = "error"
        source_file.schema_issues = [{"kind": "empty_file", "detail": "No data rows found."}]
        db.commit()
        return {"error": True, "schema_issues": source_file.schema_issues}

    source_file.status = "merged"
    source_file.row_count = total
    source_file.ingested_at = datetime.utcnow()
    db.commit()

    return {"source_file_id": str(source_file.id), "extract_type": extract_type, "rows_merged": total}
