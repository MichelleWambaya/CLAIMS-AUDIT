"""
Schema bootstrap — a no-install alternative to running `psql -f
db/schema.sql` by hand. Visiting this URL in a browser (with the right
secret) executes the schema against whatever DATABASE_URL is currently
configured.

Safe to call more than once: every statement in schema.sql uses
`IF NOT EXISTS`, so re-running it is a no-op on tables that already exist
rather than an error.

This is a deliberately narrow, single-purpose escape hatch for
environments without shell/psql access (e.g. no admin rights on the local
machine) — not a general migration system. Once schema.sql evolves beyond
initial table creation (adding columns to existing tables, etc.), this
endpoint won't pick that up; a real migration tool (Alembic) is the
correct long-term answer, noted in ARCHITECTURE.md as a Phase 2 item.
"""
import os
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import Depends

from api.db import engine, get_db
from api.models import User
from auth.security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def _check_secret(secret: str):
    expected = os.environ.get("BOOTSTRAP_SECRET")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="BOOTSTRAP_SECRET is not set on the server — set it as an "
                   "environment variable before this endpoint can be used.",
        )
    if secret != expected:
        raise HTTPException(status_code=403, detail="Incorrect secret.")


@router.get("/bootstrap-schema")
def bootstrap_schema(secret: str = Query(...)):
    _check_secret(secret)

    if not SCHEMA_PATH.exists():
        raise HTTPException(status_code=500, detail=f"schema.sql not found at {SCHEMA_PATH}")

    sql_text = SCHEMA_PATH.read_text()
    # Split on ';' at statement boundaries — schema.sql has no semicolons
    # inside string literals or function bodies, so a plain split is safe
    # here (would NOT be safe for arbitrary SQL files).
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]

    executed = 0
    errors = []
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                executed += 1
            except Exception as exc:  # noqa: BLE001 — collect, don't abort the whole run
                errors.append({"statement_preview": stmt[:80], "error": str(exc)})

    return {
        "statements_executed": executed,
        "statements_total": len(statements),
        "errors": errors,
    }


@router.get("/bootstrap-admin-user")
def bootstrap_admin_user(
    secret: str = Query(...),
    email: str = Query(...),
    password: str = Query(...),
    display_name: str = Query("Admin"),
    db: Session = Depends(get_db),
):
    """
    Same no-install pattern as bootstrap-schema, for creating the first
    login without any SQL client. Visit once with your real email/password
    as query params, then treat this endpoint as used up — it happily
    creates a second admin if called again with a different email, so
    there's no automatic self-disable, just don't leave this secret lying
    around in shared logs/screenshots (query params can end up in browser
    history and some server access logs).
    """
    _check_secret(secret)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A user with email {email} already exists.")

    user = User(
        email=email,
        display_name=display_name,
        role="admin",
        hashed_password=hash_password(password),
    )
    db.add(user)
    db.commit()

    return {"created": True, "email": user.email, "role": user.role}

