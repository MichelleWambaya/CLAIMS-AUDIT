import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Importing api.config here is what makes a missing/placeholder env var
# fail the process at startup with a clear message, before anything else
# runs — see api/config.py.
from api.config import settings
from api.db import wait_for_db, apply_schema
from api.routers import auth, sessions, flags, saved_views, reports, admin, upload, link_sync, ms_oauth

app = FastAPI(
    title="AAR Claims Forensic Audit Platform API",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(flags.router)
app.include_router(saved_views.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(upload.router)
app.include_router(link_sync.router)
app.include_router(ms_oauth.router)


@app.on_event("startup")
def on_startup():
    # Schema setup runs automatically here — never a manual SQL-console
    # step, and safe to run every time because every statement in
    # db/schema.sql is idempotent (IF NOT EXISTS).
    wait_for_db()
    apply_schema()


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Serve the built frontend from this same process ---
# The Dockerfile builds frontend/ with Vite and copies the output here.
# This is what makes "one thing to run, one thing to deploy" literally
# true: a single container serves both the API and the UI, no separate
# static host required. If FRONTEND_DIST doesn't exist (e.g. running the
# API alone for local dev against `npm run dev`), this mount is skipped.
_frontend_dist = os.environ.get("FRONTEND_DIST", "/app/frontend_dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
