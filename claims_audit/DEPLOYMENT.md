# Deployment Guide

## Why not "all on Vercel"

Vercel runs static sites and short-lived serverless functions well. This
backend needs things Vercel's serverless model doesn't provide:

- A persistent Postgres connection (serverless functions are stateless and
  spin up per-request — fine for short queries with a pooled connection,
  but this app's ingestion/report jobs run far longer than a serverless
  timeout).
- A real background job queue for OneDrive sync and large-file parsing
  (§4/§7 of the spec) — these can run for minutes on a multi-million-row
  file, well past Vercel's function time limits.
- LibreOffice-based PDF conversion (`reports/pdf_generator.py`'s
  `pptx_to_pdf`) — needs a `soffice` binary installed, not available in
  Vercel's default Node/Python runtime.

So: **frontend on Vercel, backend on something that runs long-lived
processes.**

## Recommended split

| Piece | Where | Why |
|---|---|---|
| `frontend/` | **Vercel** | Static Vite build, exactly what Vercel is for. `vercel.json` is already set up — just point `rewrites` at your real backend URL. |
| `api/` (FastAPI) | **Render / Railway / Fly.io** | All three run a persistent process with no execution-time limit, and support a `Dockerfile` or a plain `uvicorn` start command. |
| Postgres | **Neon / Supabase / Render Postgres** | Managed, free tier available on all three. |
| Redis (job queue) | **Upstash** | Free tier, works with `rq`/`celery`. |
| Object storage | **Cloudflare R2 / AWS S3** | For `generated_reports` and any manual-upload fallback. |

## Steps

1. **Deploy the backend first** (Render is the simplest for a FastAPI +
   Postgres app):
   - New Web Service → connect the GitHub repo → root directory `claims_audit`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
   - Add a Render Postgres instance, copy its connection string into
     `DATABASE_URL`
   - Set `JWT_SECRET`, `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`,
     `OBJECT_STORAGE_*` as environment variables
   - Run `psql "$DATABASE_URL" -f db/schema.sql` once, from your machine or
     Render's shell, to create the tables

2. **Deploy the frontend on Vercel:**
   - Import the GitHub repo, set the **root directory to `frontend`**
     (Vercel's project settings, not a config file)
   - Update `frontend/vercel.json`'s `rewrites` destination to your real
     Render/Railway backend URL
   - Deploy — Vercel auto-detects the Vite framework

3. **Swap the stub integrations** before this is truly production-ready:
   - `api/routers/reports.py` → `_upload_to_object_storage` currently
     returns a fake key; wire it to `boto3.put_object` or R2's S3-compatible
     SDK
   - `api/routers/sessions.py` / `reports.py` → `BackgroundTasks` should
     become real `rq` jobs against the Redis instance, per the comments
     already in those files
