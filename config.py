"""
Central configuration loader.

Hard rule (see build prompt §"No hardcoded local fallback defaults"):
required settings have NO fallback. If they're missing, the app refuses
to start and says exactly which variable is missing — instead of silently
connecting to a localhost database/secret that only ever made sense on a
developer's laptop.

Every setting the app reads must be declared here, once, so
`.env.example` and this file never drift apart.
"""
import os
import sys


class ConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"See .env.example for what it's for and set it before starting the app."
        )
    return val


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


class Settings:
    def __init__(self):
        # --- Database (no fallback — a missing DATABASE_URL must fail loudly) ---
        self.DATABASE_URL = _require("DATABASE_URL")

        # --- Auth ---
        self.JWT_SECRET = _require("JWT_SECRET")
        if self.JWT_SECRET in ("dev-secret-change-me", "change-me-to-a-long-random-string"):
            raise ConfigError(
                "JWT_SECRET is set to a known placeholder value. Generate a real "
                "secret, e.g.: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        self.JWT_ALGORITHM = "HS256"
        self.JWT_EXPIRES_MINUTES = int(_optional("JWT_EXPIRES_MINUTES", "480"))
        self.ALLOW_SELF_SIGNUP = _optional("ALLOW_SELF_SIGNUP", "true").lower() == "true"
        # First self-signup on an empty users table becomes admin automatically,
        # so there's always a real account-creation path and never a bootstrap
        # HTTP endpoint hit by hand in a browser address bar.

        # --- Storage for generated reports ---
        # Self-contained default: local disk inside the container, backed by a
        # Docker volume (see docker-compose.yml). Set STORAGE_BACKEND=s3 and the
        # S3_* vars below to use real object storage instead (e.g. for the
        # cloud-deploy path).
        self.STORAGE_BACKEND = _optional("STORAGE_BACKEND", "local")
        self.LOCAL_STORAGE_DIR = _optional("LOCAL_STORAGE_DIR", "/data/reports")
        # Shared between the app and worker containers (see docker-compose.yml)
        # so a file streamed to disk by the API process is actually visible to
        # the worker process that later parses it — /tmp is NOT shared across
        # containers, this must be a real mounted volume.
        self.UPLOAD_TMP_DIR = _optional("UPLOAD_TMP_DIR", "/data/uploads")
        if self.STORAGE_BACKEND == "s3":
            self.S3_BUCKET = _require("S3_BUCKET")
            self.S3_ENDPOINT = _optional("S3_ENDPOINT")
            self.S3_ACCESS_KEY = _require("S3_ACCESS_KEY")
            self.S3_SECRET_KEY = _require("S3_SECRET_KEY")
            self.S3_REGION = _optional("S3_REGION", "auto")

        # --- Background jobs ---
        self.REDIS_URL = _require("REDIS_URL")

        # --- Microsoft Graph / OneDrive connectivity (all optional — each of
        # the 3 ingestion paths degrades to "unavailable, here's why" if its
        # own vars aren't set, rather than the app refusing to start) ---
        self.MS_TENANT_ID = _optional("MS_TENANT_ID")
        self.MS_CLIENT_ID = _optional("MS_CLIENT_ID")
        self.MS_CLIENT_SECRET = _optional("MS_CLIENT_SECRET")
        # Delegated OAuth redirect target — must match the app registration.
        self.MS_OAUTH_REDIRECT_URI = _optional("MS_OAUTH_REDIRECT_URI")

        self.CORS_ORIGINS = [
            o.strip() for o in _optional("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
        ]

    def graph_app_only_configured(self) -> bool:
        return bool(self.MS_TENANT_ID and self.MS_CLIENT_ID and self.MS_CLIENT_SECRET)

    def graph_delegated_configured(self) -> bool:
        return bool(self.MS_TENANT_ID and self.MS_CLIENT_ID and self.MS_CLIENT_SECRET and self.MS_OAUTH_REDIRECT_URI)


try:
    settings = Settings()
except ConfigError as e:
    # Fail fast and clearly, at import time, before anything tries to use a
    # half-configured app. This is what turns "stack trace three layers deep
    # in a connection pool" into a one-line, actionable message.
    sys.stderr.write(f"\nCONFIGURATION ERROR: {e}\n\n")
    raise
