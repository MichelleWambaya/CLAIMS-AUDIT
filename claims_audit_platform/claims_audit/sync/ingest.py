"""
Ingest orchestration — the background job body that a queue worker
(RQ/BullMQ/Celery, whichever the API layer settles on) invokes per
audit session sync.

Flow (§4 requirements: progress, per-file schema errors, sheet selection,
resumable at the file level):
  1. Ask Graph for what changed in the configured folder since last sync.
  2. For each changed file:
     a. Determine extract type (claim-level vs item-level) from headers.
     b. Validate required columns are present -> record schema_issues,
        skip merge on failure (never silently drop the file).
     c. Stream-parse rows, map columns via alias lookup, insert into
        claim_rows in batches, updating progress as it goes.
  3. Persist the new delta token so the next sync only looks at changes.

This module is intentionally storage-agnostic: `db` is anything exposing
the few methods below, so it drops into SQLAlchemy, asyncpg, or a plain
psycopg2 connection wrapper without change.
"""
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from .graph_client import GraphClient, DriveItem
from .streaming_parser import stream_csv_rows, stream_excel_rows, validate_required_columns
from rules.column_mapping import map_headers, DEFAULT_ALIASES

CLAIM_LEVEL_REQUIRED = ["member_id", "policy_number", "claim_code"]
ITEM_LEVEL_REQUIRED = ["member_id", "product_name", "visit_date", "item_status"]

BATCH_SIZE = 5000


class SessionStore(Protocol):
    """Minimal interface the ingest job needs from storage — implement
    this against Postgres/SQLAlchemy in the real API layer."""

    def create_source_file(self, audit_session_id: str, drive_item: DriveItem, extract_type: Optional[str]) -> str: ...
    def update_source_file_status(self, source_file_id: str, status: str, schema_issues: Optional[list] = None): ...
    def insert_claim_rows_batch(self, audit_session_id: str, source_file_id: str, rows: list): ...
    def save_delta_link(self, audit_session_id: str, delta_link: str): ...
    def get_delta_link(self, audit_session_id: str) -> Optional[str]: ...
    def report_progress(self, source_file_id: str, rows_processed: int, rows_total: Optional[int]): ...


def _detect_extract_type(mapped_fields_present: set) -> str:
    if {"product_name", "visit_date", "item_status"} & mapped_fields_present:
        return "item_level"
    return "claim_level"


def sync_audit_session(
    session_store: SessionStore,
    graph: GraphClient,
    audit_session_id: str,
    drive_id: str,
    folder_path: str,
    sheet_selector: Optional[Callable[[DriveItem, list], str]] = None,
):
    """
    sheet_selector: optional callback (drive_item, sheet_names) -> chosen
    sheet name, for workbooks with multiple tabs. Defaults to the first
    non-empty-looking sheet if not provided — but §4 wants this to be a
    real UI choice, so the API layer should normally supply one backed by
    a user decision, not silently default.
    """
    prior_delta = session_store.get_delta_link(audit_session_id)
    changed_items, next_delta = graph.list_folder_delta(drive_id, folder_path, prior_delta)

    for item in changed_items:
        if item.is_folder:
            continue
        _ingest_one_file(session_store, graph, audit_session_id, item, sheet_selector)

    session_store.save_delta_link(audit_session_id, next_delta)


def _ingest_one_file(
    session_store: SessionStore,
    graph: GraphClient,
    audit_session_id: str,
    item: DriveItem,
    sheet_selector: Optional[Callable[[DriveItem, list], str]],
):
    is_excel = item.name.lower().endswith((".xlsx", ".xlsm", ".xls"))
    source_file_id = session_store.create_source_file(audit_session_id, item, extract_type=None)
    session_store.update_source_file_status(source_file_id, "parsing")

    try:
        if is_excel:
            rows_iter, schema_issues, extract_type = _parse_excel(graph, item, sheet_selector)
        else:
            rows_iter, schema_issues, extract_type = _parse_csv(graph, item)

        if schema_issues:
            session_store.update_source_file_status(
                source_file_id, "error", schema_issues=[i.to_dict() for i in schema_issues]
            )
            return

        batch = []
        processed = 0
        for raw_row in rows_iter:
            mapped_row = _map_and_normalize(raw_row, extract_type)
            batch.append(mapped_row)
            processed += 1
            if len(batch) >= BATCH_SIZE:
                session_store.insert_claim_rows_batch(audit_session_id, source_file_id, batch)
                session_store.report_progress(source_file_id, processed, None)
                batch = []

        if batch:
            session_store.insert_claim_rows_batch(audit_session_id, source_file_id, batch)
            session_store.report_progress(source_file_id, processed, processed)

        session_store.update_source_file_status(source_file_id, "merged")

    except Exception as exc:  # noqa: BLE001 — surface any parse failure as a per-file error, don't crash the whole sync
        session_store.update_source_file_status(
            source_file_id, "error", schema_issues=[{"kind": "exception", "detail": str(exc)}]
        )


def _parse_csv(graph: GraphClient, item: DriveItem):
    peek_rows = []
    row_gen = stream_csv_rows(graph.stream_download(item))
    for row in row_gen:
        peek_rows.append(row)
        if len(peek_rows) >= 1:
            break
    if not peek_rows:
        return iter([]), [], "claim_level"

    headers = list(peek_rows[0].keys())
    mapped = map_headers(headers, DEFAULT_ALIASES)
    present = set(v for v in mapped.values() if v)
    extract_type = _detect_extract_type(present)
    required = ITEM_LEVEL_REQUIRED if extract_type == "item_level" else CLAIM_LEVEL_REQUIRED
    issues = validate_required_columns(present, required)

    def _chain():
        yield from peek_rows
        yield from row_gen

    return _chain(), issues, extract_type


def _parse_excel(graph: GraphClient, item: DriveItem, sheet_selector):
    import io
    # Excel needs random access for openpyxl, so buffer to a spooled temp
    # file rather than true streaming from the network — still never puts
    # the parsed *rows* fully in memory, which is where the real cost is
    # for multi-million-row sheets.
    import tempfile
    spool = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)
    for chunk in graph.stream_download(item):
        spool.write(chunk)
    spool.seek(0)

    from .streaming_parser import list_workbook_sheets
    sheet_names = list_workbook_sheets(spool)
    spool.seek(0)
    chosen_sheet = sheet_selector(item, sheet_names) if sheet_selector else sheet_names[0]

    rows_iter, issues = stream_excel_rows(spool, chosen_sheet)
    if issues:
        return iter([]), issues, "claim_level"

    first_batch = []
    for row in rows_iter:
        first_batch.append(row)
        break
    if not first_batch:
        return iter([]), [], "claim_level"

    headers = list(first_batch[0].keys())
    mapped = map_headers(headers, DEFAULT_ALIASES)
    present = set(v for v in mapped.values() if v)
    extract_type = _detect_extract_type(present)
    required = ITEM_LEVEL_REQUIRED if extract_type == "item_level" else CLAIM_LEVEL_REQUIRED
    col_issues = validate_required_columns(present, required)

    def _chain():
        yield from first_batch
        yield from rows_iter

    return _chain(), col_issues, extract_type


def _map_and_normalize(raw_row: dict, extract_type: str) -> dict:
    mapped = map_headers(list(raw_row.keys()), DEFAULT_ALIASES)
    out = {"extract_type": extract_type, "raw_extra": {}}
    for raw_key, value in raw_row.items():
        canonical = mapped.get(raw_key)
        if canonical:
            out[canonical] = value
        else:
            out["raw_extra"][raw_key] = value
    out["_has_item_status_column"] = "item_status" in mapped.values()
    return out
