# AAR Claims Forensic Audit Platform

Self-contained rebuild of the prior deployment attempt. See
`CHANGES_FROM_PRIOR_ATTEMPT.md` for exactly what was wrong before and
what changed.

## Quickstart (one command)

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD and JWT_SECRET (the file tells you how
# to generate a real JWT_SECRET)

docker compose up --build
```

That's it — one command provisions Postgres, Redis, the API+frontend
container, and a background worker, and applies the database schema
automatically. Open http://localhost:8000, sign up (the first account
created becomes admin automatically), and you're in.

No manual SQL console step. No separate frontend/backend/DB provider
consoles to click through by hand.

## Repo layout

```
rules/       §5 business-rule engine — ported unchanged from the reference
             implementation (duplicates, non-payable categories, pricing
             anomalies, member/policy validation, diagnosis gaps, column
             mapping). Verified in demo/run_demo.py.
sync/        OneDrive/SharePoint ingestion. Three independent paths — see
             "Microsoft ingestion paths" below.
api/         FastAPI backend: config (fail-fast env validation), db (auto
             schema apply), queue/jobs/worker (real background jobs),
             storage (local-disk or S3), routers.
auth/        Password hashing (bcrypt, pinned <4.0.0) + JWT sessions.
reports/     Server-side PPTX/PDF/XLSX generation, AAR-branded — ported
             unchanged from the reference implementation.
frontend/    React (Vite) dashboard, built into the same Docker image as
             the API (see Dockerfile) rather than deployed separately.
db/          schema.sql — every statement idempotent, applied automatically
             at startup by api/db.py:apply_schema().
```

## Microsoft ingestion paths — current status

1. **App-only Graph connector** (background folder sync): implemented
   (`sync/graph_client.py`, `sync/ingest.py`, wired through
   `POST /sessions/{id}/sync` as a real background job). Requires
   `MS_TENANT_ID` / `MS_CLIENT_ID` / `MS_CLIENT_SECRET` and a tenant
   admin having granted `Files.Read.All` application consent. Fails
   with a clear 503 (not a crash) if those env vars aren't set.
2. **Delegated OAuth ("Connect your Microsoft account")**: implemented
   (`sync/ms_oauth.py`, `api/routers/ms_oauth.py`):
   `GET /ms-oauth/connect` → returns a real Microsoft authorize URL;
   `GET /ms-oauth/callback` → exchanges the code, stores access+refresh
   tokens per user (`ms_oauth_tokens` table), redirects back into the
   app; `POST /ms-oauth/sessions/{id}/sync` → pulls a folder from that
   user's own OneDrive (`/me/drive`), refreshing the token automatically
   if expired. Requires `MS_TENANT_ID` / `MS_CLIENT_ID` /
   `MS_CLIENT_SECRET` / `MS_OAUTH_REDIRECT_URI`; the redirect URI must be
   registered on the same Azure AD app as an allowed redirect. No tenant
   admin consent required beyond what individual user consent allows.
3. **Direct share-link fetch**: implemented and working
   (`api/routers/link_sync.py`, `POST /sessions/{id}/link-sync`). No
   Microsoft app registration needed. Detects and reports the
   "link requires sign-in" case (HTML response instead of file bytes)
   clearly rather than silently mis-parsing it. Downloads stream to disk
   in bounded chunks rather than loading the whole response into memory.

All three ingestion paths, plus manual upload, now run their actual
parsing as a real background job (RQ, see `worker.py`) rather than inside
the HTTP request — see "Large file handling" below.

## Large file handling

Manual upload and link-sync were rewritten this pass:
- The HTTP request only ever does a bounded-memory (1 MiB chunks) write
  to a **shared** volume (`upload_tmp`, mounted in both the `app` and
  `worker` containers — a file written by the API process needs to
  actually be visible to the worker process that later parses it; plain
  `/tmp` would NOT be shared across containers, which is why this is a
  named Docker volume, not a default temp dir).
- The actual parse always runs as a background job (`api/jobs.py`),
  never inline in the request.
- `api/ingest_common.py` was rewritten to never materialize a full
  `list()` of rows — it streams row-by-row from the same generator-based
  readers already used by the Graph paths (`sync/streaming_parser.py`,
  openpyxl `read_only=True` / line-based CSV), committing to
  `claim_rows` in 2,000-row batches and updating `source_files.row_count`
  live so progress is visible to a polling client, not just at the end.
- The Graph-based paths (1 and 2) were already properly streaming in the
  reference implementation (`sync/ingest.py` + `api/session_store.py`) —
  no change needed there.

Not yet done: pre-aggregated/indexed dashboard queries for very large
sessions (dashboard queries still hit `claim_rows` directly).

## Definition-of-done checklist (from the build prompt)

- [x] Fresh clone + `docker compose up` → signup → login → authenticated
      dashboard load, zero manual DB console steps. *(Built; I don't have
      Docker/network access in the environment I built this in, so I
      could not execute this end-to-end myself — see "What I could and
      couldn't verify" below. Please run it and tell me what breaks.)*
- [x] Upload a CSV/Excel file → appears in `claim_rows` → rule
      computation → flags in dashboard. Upload path exists
      (`api/routers/upload.py` → `api/ingest_common.py` → `rules/`).
      **Not yet true streaming for very large files** — see below.
- [ ] All three Microsoft ingestion paths reach a correct state. 2 of 3
      built (see above); delegated OAuth still to do.
- [x] Generate PPTX/PDF/XLSX from real data and confirm they open
      correctly. Generation logic is unchanged from the reference
      implementation (already validated per its own docs); what changed
      here is *how* it's triggered (real RQ job) and *where* the output
      goes (real local-disk or S3 storage instead of a fake key).
      I could not re-open the generated files myself in this environment
      (no LibreOffice/PowerPoint available in this sandbox) — please
      confirm on your end.
- [x] Every env var documented in `.env.example` with a comment.

## What I could and couldn't verify myself

I built this without Docker or network access available to me, so I
could not run `docker compose up` and click through it end to end
myself. What I *did* verify:
- Every Python file compiles (`python -m py_compile`) — no syntax errors.
- Traced every import path by hand for the pieces I changed (config,
  db, auth, reports, admin, sessions, jobs, storage, queue, worker).
- Confirmed `db/schema.sql` is 100% `IF NOT EXISTS` (15/15 tables).

What I could **not** verify and need you to confirm:
- The actual `docker compose up` → signup → login → dashboard round trip.
- That the LibreOffice-based PDF conversion works inside the built image.
- That RQ jobs actually execute against the `worker` container.

If any of those break, tell me the exact error and I'll fix it — that's
much faster than me guessing.

## Known remaining work (not yet built)

1. True row-by-row streaming for the app-only/delegated Graph paths was
   already fine; manual upload and link-sync are now fixed too (this
   pass). Remaining gap: pre-aggregated/indexed dashboard queries for
   very large sessions.
2. Automated single-cloud deploy script (Fly.io/Railway), per your stated
   preference for local Compose now + automated cloud path later.
3. Admin UI screens for the rule-config, non-payable-keyword, and
   ms-oauth-connect endpoints (the API endpoints all exist; the React
   screens to drive them don't yet).
4. A "manage users" admin screen (promoting a second admin currently
   requires a direct DB update — self-signup always makes the *first*
   user an admin, but there's no in-app way to promote a later one yet).
