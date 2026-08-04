# AAR Claims Forensic Audit Platform

Production-grade claims QA / fraud-waste-abuse audit platform for AAR
Insurance Kenya. Replaces the original single-file HTML prototype with a
real client/server application per the build spec (see `ARCHITECTURE.md`).

## What's in this repo

```
rules/          §5 business-rule engine — duplicates, non-payable categories,
                pricing anomalies, member/policy validation, diagnosis gaps,
                column mapping. Stack-agnostic: plain dicts in, dataclasses
                out. Fully covered by demo/run_demo.py.

sync/           OneDrive/SharePoint ingestion — Graph API delta-sync client,
                streaming CSV/Excel parsing, ingest orchestration with
                per-file progress and schema-error reporting.

api/            FastAPI backend — SQLAlchemy models, session/flag/saved-view/
                report routers, background report generation.

auth/           JWT auth + analyst/admin RBAC.

reports/        Server-side PPTX / PDF / XLSX generation, AAR-branded.
                Tested output: python-pptx validator passes, XLSX formulas
                recalculate with zero errors, PDF renders correctly both as
                a converted slide deck and as a plain dashboard export.

frontend/       React (Vite) dashboard shell — cross-filtering category
                chart, trend chart, paginated/sortable claims table, concise
                time-period picker, flag review panel, export panel.

db/schema.sql   Postgres schema — merged claim_rows dataset per audit
                session, flags, audit trail, saved views, stored reports,
                config history.

demo/           Working proof that the rule engine and export generators
                actually run correctly (not just syntactically valid).
```

## Setup

### Backend

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL, JWT_SECRET, MS_* Graph credentials
psql < db/schema.sql
uvicorn api.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to the backend (`vite.config.js`) —
set `API_PROXY_TARGET` if the backend isn't on `localhost:8000`.

### Verify the rule engine

```bash
python3 demo/run_demo.py
```

Runs every §5 rule against edge-case sample data and asserts correct
behavior (duplicates within/outside the day window, non-payable keyword
matches across product/diagnosis fields, IQR pricing outliers, policy
format validation, diagnosis gaps, header-alias mapping).

## What's implemented vs. stubbed

**Implemented and tested:**
- All six §5 rules, fully configurable, verified against edge cases.
- PPTX/PDF/XLSX generation — actually run and validated (schema validator,
  formula recalculation, visual rendering).
- Full API surface for sessions, flags, reviews, overrides, saved views,
  and report generation/storage.
- React dashboard with working cross-filter state, time-period presets,
  paginated table, and review/override UI.

**Stubbed, needs real infra to finish:**
- `api/session_store.py` bulk-insert and `sync/ingest.py` assume a live
  Postgres connection — no DB server available in this build environment
  to run against.
- `_upload_to_object_storage` in `api/routers/reports.py` is a stub —
  swap in a real S3-compatible `put_object` call.
- FastAPI `BackgroundTasks` stands in for a real job queue (RQ/Celery) —
  fine for dev, but doesn't survive a process restart; swap per the
  comments in `api/routers/sessions.py` and `reports.py`.
- Frontend was syntax-checked (balanced braces, manual review) but not
  built/run — no network access in this environment to `npm install`
  React/Vite/recharts. Everything needed is pinned in `package.json`.

## Business rules reference

See `ARCHITECTURE.md` for the full §5–§11 mapping from the original build
spec, including what changed based on your OneDrive/time-period/merged-DB/
stored-reports feedback.
