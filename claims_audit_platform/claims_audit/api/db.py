import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://claims_audit:changeme@localhost:5432/claims_audit"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = int(os.environ.get("JWT_EXPIRES_MINUTES", "480"))

OBJECT_STORAGE_BUCKET = os.environ.get("OBJECT_STORAGE_BUCKET", "claims-audit-reports")
OBJECT_STORAGE_ENDPOINT = os.environ.get("OBJECT_STORAGE_ENDPOINT")  # S3-compatible endpoint
