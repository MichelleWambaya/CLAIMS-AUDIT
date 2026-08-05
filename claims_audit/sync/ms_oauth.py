"""
Delegated OAuth for the "Connect your Microsoft account" ingestion path
(path 2 of 3 — see build prompt). Distinct from GraphClient's app-only
client-credentials flow: here the *signed-in user* consents for
themselves via a standard Microsoft login/consent screen, so no tenant
admin involvement is required unless the org has blocked user consent
entirely.

Uses the same Azure AD app registration (MS_TENANT_ID / MS_CLIENT_ID /
MS_CLIENT_SECRET) as the app-only path, plus MS_OAUTH_REDIRECT_URI, which
must be registered on that app as a valid redirect URI.
"""
import time
from typing import Optional

import requests

from api.config import settings

AUTHORITY = "https://login.microsoftonline.com"
SCOPES = "offline_access Files.Read Files.Read.All User.Read"


def build_authorize_url(state: str) -> str:
    from urllib.parse import urlencode
    params = {
        "client_id": settings.MS_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.MS_OAUTH_REDIRECT_URI,
        "response_mode": "query",
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTHORITY}/{settings.MS_TENANT_ID}/oauth2/v2.0/authorize?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict:
    resp = requests.post(
        f"{AUTHORITY}/{settings.MS_TENANT_ID}/oauth2/v2.0/token",
        data={
            "client_id": settings.MS_CLIENT_ID,
            "client_secret": settings.MS_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.MS_OAUTH_REDIRECT_URI,
            "scope": SCOPES,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    resp = requests.post(
        f"{AUTHORITY}/{settings.MS_TENANT_ID}/oauth2/v2.0/token",
        data={
            "client_id": settings.MS_CLIENT_ID,
            "client_secret": settings.MS_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": SCOPES,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


class DelegatedGraphClient:
    """Same shape of interface as sync.graph_client.GraphClient's download
    helpers, but authenticated as the signed-in user against their own
    OneDrive (/me/drive) rather than an app-only client against an
    arbitrary drive id."""

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def list_my_folder_delta(self, folder_path: str, delta_link: Optional[str] = None):
        from sync.graph_client import DriveItem
        url = delta_link or f"{self.GRAPH_BASE}/me/drive/root:/{folder_path}:/delta"
        items = []
        delta_out = None
        next_link = url
        while next_link:
            resp = requests.get(next_link, headers=self._headers(), timeout=60)
            resp.raise_for_status()
            body = resp.json()
            for raw in body.get("value", []):
                if raw.get("deleted"):
                    continue
                items.append(DriveItem(
                    id=raw["id"], name=raw["name"], web_url=raw.get("webUrl", ""),
                    size_bytes=raw.get("size", 0), etag=raw.get("eTag", ""),
                    download_url=raw.get("@microsoft.graph.downloadUrl"),
                    is_folder="folder" in raw,
                ))
            next_link = body.get("@odata.nextLink")
            delta_out = body.get("@odata.deltaLink")
        return items, delta_out

    def list_folder_delta(self, drive_id: str, folder_path: str, delta_link: Optional[str] = None):
        """Adapter matching GraphClient.list_folder_delta's signature so
        sync.ingest.sync_audit_session can drive either client
        interchangeably. `drive_id` is ignored here — delegated tokens
        always operate against the signed-in user's own drive (/me/drive)."""
        return self.list_my_folder_delta(folder_path, delta_link)

    def stream_download(self, item, chunk_size: int = 8 * 1024 * 1024):
        if not item.download_url:
            raise ValueError(f"No download URL for item {item.id} — re-fetch item metadata")
        with requests.get(item.download_url, stream=True, timeout=None) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    yield chunk
