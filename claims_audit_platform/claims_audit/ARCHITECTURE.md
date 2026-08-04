# Claims Forensic Audit Platform — Architecture (v2)

Updates from the original build prompt based on your feedback:

## 1. Ingestion: OneDrive/SharePoint connector, not manual upload

- Files live in shared OneDrive/SharePoint folders. Ingestion uses the
  **Microsoft Graph API** (delta query on the target folder) to detect new
  or changed files — no drag-and-drop upload UI.
- This does **not** remove the large-file constraint from §4 of the original
  spec: a multi-hundred-MB workbook pulled from OneDrive still has to be
  streamed and parsed server-side, row-by-row, in a background worker. What
  it removes is the client-side upload/chunking problem — Graph API handles
  the transfer, our worker handles the parse.
- Flow: **scheduled/webhook-triggered sync job** → list changed files in the
  configured folder(s) → download stream → schema validation (§4) → parse →
  write into `claim_rows` for the audit session → mark `source_files.status
  = 'merged'`.
- Re-syncs are idempotent: a file already ingested at a given version/etag
  is skipped, so re-running a sync doesn't duplicate rows.
- Manual upload stays available as a fallback path (`source_type =
  'manual_upload'` in the schema) for one-off files not in a synced folder,
  but it's no longer the primary path.

## 2. Time period: concise picker, not a full BI axis config

Replaces the heavier "arbitrary time dimension" idea with a compact
control: a handful of presets (**This Month, Last Month, This Quarter,
Last Quarter, YTD, All Time**) plus one **custom range**. This drives every
visual and the export snapshot. Internally it's still just a `date_from` /
`date_to` filter applied at the query layer — simple to reason about, simple
to extend later if a genuine need for finer-grained time controls shows up.

## 3. Merged database

- One canonical `claim_rows` table per `audit_session`, populated from every
  ingested `source_files` batch (see `db/schema.sql`).
- Column mapping (§5.6) happens at ingest time, before rows ever land in
  `claim_rows` — so the merge is on canonical fields, and cross-batch
  duplicate/rule checks (e.g. a duplicate spanning two different monthly
  files) work naturally, not just within a single upload.
- Unmapped/unexpected columns are preserved in `raw_extra` (JSONB) rather
  than dropped, so nothing from the source file is silently lost even if a
  rule doesn't use it.

## 4. Dashboards & presentations are generated **and stored**

- `generated_reports` table (see schema) persists every PPTX/PDF/XLSX export
  with its object-storage key, status, and who generated it — so past
  reports are browsable in-app, not just a one-time download link.
- Same pattern for dashboard state: `saved_views` stores a named filter/time-range/
  dimension configuration an analyst can return to or hand to a colleague.
- Report generation still runs as a background job (large sessions can have
  a lot of rows to summarize) with `status: queued → generating → ready`,
  polled or pushed to the UI.

## 5. Everything else from the original spec is unchanged

Rule logic (§5), non-functional targets (§10), MVP/Phase 2 split (§11), and
branding (§9) all carry over as originally specified. The rule engine
(`rules/`) is intentionally backend-agnostic — it takes plain dicts in and
returns dataclasses out, so it drops into whatever API framework (FastAPI,
Express, etc.) ends up on the sync/parse worker without modification.

## 6. What's built so far

- `rules/` — full §5 rule engine (duplicates, non-payable, pricing
  anomalies, member/policy validation, diagnosis gaps, column mapping),
  every threshold configurable via `RuleConfig`, verified against edge
  cases in `demo/run_demo.py`.
- `db/schema.sql` — Postgres schema for the merged dataset, flags, audit
  trail, saved views, and stored reports, matching this document.

## 7. Not yet built (next steps, in rough priority order)

1. OneDrive/SharePoint sync worker (Graph API client + delta query + streaming
   parse into `claim_rows`).
2. API layer (FastAPI/Express) exposing sessions, flags, review actions,
   saved views, report generation — thin wrapper over `rules/` + Postgres.
3. React dashboard shell (cross-filtering charts + the time-period picker
   from §2 + paginated claims table).
4. PPTX/PDF/XLSX generation service, AAR-branded, running as a background
   job against `generated_reports`.
5. Auth + RBAC (analyst/admin) and the access log.
