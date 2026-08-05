"""
Ingestion path 2 of 3: delegated OAuth ("Connect your Microsoft account").

Flow:
  1. Frontend calls GET /ms-oauth/connect -> gets an authorize_url, redirects
     the browser to it.
  2. User signs in and consents on Microsoft's real login page.
  3. Microsoft redirects back to MS_OAUTH_REDIRECT_URI, which points at
     GET /ms-oauth/callback?code=...&state=... — we exchange the code for
     tokens and store them against the user who initiated the flow.
  4. Frontend can then call POST /sessions/{id}/ms-oauth-sync to pull a
     folder from *that user's own* OneDrive, no tenant admin involved.

`state` carries the initiating user's id, signed the same way login
sessions are (HS256 JWT with the app's JWT_SECRET), so the callback -
which arrives as a plain unauthenticated browser redirect, not an API
call with an Authorization header - can still be tied back to the right
account without a separate server-side session store.
"""
import uuid
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.models import User, MsOAuthToken, SourceFile
from api.queue import default_queue
from auth.security import get_current_user
from sync.ms_oauth import build_authorize_url, exchange_code_for_token, refresh_access_token

router = APIRouter(prefix="/ms-oauth", tags=["ms-oauth"])


def _configured():
    return bool(settings.MS_TENANT_ID and settings.MS_CLIENT_ID and settings.MS_CLIENT_SECRET
                and settings.MS_OAUTH_REDIRECT_URI)


@router.get("/status")
def oauth_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not _configured():
        return {"configured": False, "connected": False,
                "reason": "MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET / MS_OAUTH_REDIRECT_URI "
                          "not all set on this deployment."}
    token = db.query(MsOAuthToken).filter(MsOAuthToken.user_id == user.id).first()
    return {"configured": True, "connected": token is not None}


@router.get("/connect")
def connect(user: User = Depends(get_current_user)):
    if not _configured():
        raise HTTPException(
            status_code=503,
            detail="Delegated Microsoft sign-in isn't configured on this deployment "
                   "(missing MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET / MS_OAUTH_REDIRECT_URI).",
        )
    state = jwt.encode(
        {"uid": str(user.id), "exp": datetime.utcnow() + timedelta(minutes=10)},
        settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM,
    )
    return {"authorize_url": build_authorize_url(state)}


@router.get("/callback")
def callback(code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload["uid"]
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state — please try connecting again.")

    try:
        token_resp = exchange_code_for_token(code)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Microsoft token exchange failed: {exc}")

    expires_at = datetime.utcnow() + timedelta(seconds=token_resp.get("expires_in", 3600))
    existing = db.query(MsOAuthToken).filter(MsOAuthToken.user_id == user_id).first()
    if existing:
        existing.access_token = token_resp["access_token"]
        existing.refresh_token = token_resp.get("refresh_token", existing.refresh_token)
        existing.expires_at = expires_at
        existing.scope = token_resp.get("scope")
        existing.updated_at = datetime.utcnow()
    else:
        db.add(MsOAuthToken(
            user_id=user_id, access_token=token_resp["access_token"],
            refresh_token=token_resp.get("refresh_token", ""), expires_at=expires_at,
            scope=token_resp.get("scope"),
        ))
    db.commit()

    # Hand back to the frontend so the user sees a normal in-app state
    # rather than a bare JSON blob after the Microsoft redirect.
    return RedirectResponse(url="/?ms_connected=1")


def get_valid_access_token(db: Session, user_id) -> str:
    token = db.query(MsOAuthToken).filter(MsOAuthToken.user_id == user_id).first()
    if not token:
        raise HTTPException(status_code=409, detail="Microsoft account not connected. Call /ms-oauth/connect first.")
    if token.expires_at <= datetime.utcnow():
        refreshed = refresh_access_token(token.refresh_token)
        token.access_token = refreshed["access_token"]
        token.refresh_token = refreshed.get("refresh_token", token.refresh_token)
        token.expires_at = datetime.utcnow() + timedelta(seconds=refreshed.get("expires_in", 3600))
        db.commit()
    return token.access_token


from pydantic import BaseModel


class DelegatedSyncRequest(BaseModel):
    folder_path: str


@router.post("/sessions/{session_id}/sync")
def delegated_sync(session_id: str, body: DelegatedSyncRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Pulls a folder from the signed-in user's own OneDrive using their
    delegated token — runs as a background job, same as the app-only path."""
    access_token = get_valid_access_token(db, user.id)  # raises 409 if not connected, 502 if refresh fails

    from api.models import AuditSession
    if not db.query(AuditSession).filter(AuditSession.id == session_id).first():
        raise HTTPException(status_code=404, detail="Session not found")

    from api.jobs import run_delegated_graph_sync_job
    default_queue.enqueue(
        run_delegated_graph_sync_job, session_id, str(user.id), body.folder_path,
        job_timeout="2h",
    )
    return {"status": "sync_started"}
