import os
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from api.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Re-exported so existing imports (`from api.db import JWT_SECRET`, etc.)
# elsewhere in the codebase keep working without change.
JWT_SECRET = settings.JWT_SECRET
JWT_ALGORITHM = settings.JWT_ALGORITHM
JWT_EXPIRES_MINUTES = settings.JWT_EXPIRES_MINUTES


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(max_attempts: int = 30, delay_seconds: float = 2.0) -> None:
    """Retry the initial connection instead of crashing on the first attempt —
    useful when the DB container is still starting up under docker-compose."""
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as e:
            last_err = e
            sys.stderr.write(
                f"Database not reachable yet (attempt {attempt}/{max_attempts}), retrying in {delay_seconds}s...\n"
            )
            time.sleep(delay_seconds)
    raise RuntimeError(
        f"Could not connect to the database at DATABASE_URL after {max_attempts} attempts. "
        f"Last error: {last_err}"
    )


def apply_schema() -> None:
    """Run db/schema.sql automatically. Every statement in that file is
    idempotent (CREATE TABLE/INDEX IF NOT EXISTS), so this is safe to run on
    every startup — no manual psql/SQL-console step, ever."""
    schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
    with open(schema_path, "r") as f:
        schema_sql = f.read()
    with engine.begin() as conn:
        conn.execute(text(schema_sql))
