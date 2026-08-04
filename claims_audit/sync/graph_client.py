"""
Microsoft Graph API client for OneDrive/SharePoint ingestion.

Auth: client-credentials flow (app-only) against a configured Azure AD app
with Files.Read.All / Sites.Read.All, since this runs unattended as a
background sync job rather than acting as an individual signed-in user.

Uses delta queries so re-syncs only fetch what changed since the last
sync token — cheap to run frequently instead of re-listing an entire
shared folder every time.
"""
import os
import time
from dataclasses import dataclass
from typing import Iterator, Optional

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


@dataclass
class DriveItem:
    id: str
    name: str
    web_url: str
    size_bytes: int
    etag: str
    download_url: Optional[str]  # @microsoft.graph.downloadUrl, short-lived
    is_folder: bool


class GraphClient:
    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self.tenant_id = tenant_id or os.environ["MS_TENANT_ID"]
        self.client_id = client_id or os.environ["MS_CLIENT_ID"]
        self.client_secret = client_secret or os.environ["MS_CLIENT_SECRET"]
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        resp = requests.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires_at = time.time() + body["expires_in"]
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def list_folder_delta(
        self, drive_id: str, folder_path: str, delta_link: Optional[str] = None
    ) -> "tuple[list[DriveItem], str]":
        """
        Returns (changed_items, next_delta_link). Pass the previous
        next_delta_link back in on the following sync to get only what
        changed. Pass delta_link=None for the initial full sync.
        """
        if delta_link:
            url = delta_link
        else:
            url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{folder_path}:/delta"

        items: list[DriveItem] = []
        next_link = url

        while next_link:
            resp = requests.get(next_link, headers=self._headers(), timeout=60)
            resp.raise_for_status()
            body = resp.json()

            for raw in body.get("value", []):
                if raw.get("deleted"):
                    continue  # deletion handling: mark source_files inactive, not covered here
                is_folder = "folder" in raw
                items.append(DriveItem(
                    id=raw["id"],
                    name=raw["name"],
                    web_url=raw.get("webUrl", ""),
                    size_bytes=raw.get("size", 0),
                    etag=raw.get("eTag", ""),
                    download_url=raw.get("@microsoft.graph.downloadUrl"),
                    is_folder=is_folder,
                ))

            next_link = body.get("@odata.nextLink")
            delta_out = body.get("@odata.deltaLink")

        return items, delta_out

    def stream_download(self, item: DriveItem, chunk_size: int = 8 * 1024 * 1024) -> Iterator[bytes]:
        """
        Streams file bytes in chunks so large workbooks never sit fully in
        memory. `download_url` is a pre-authenticated, short-lived URL
        Graph returns alongside each item — no auth header needed on it.
        """
        if not item.download_url:
            raise ValueError(f"No download URL for item {item.id} — re-fetch item metadata")
        with requests.get(item.download_url, stream=True, timeout=None) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    yield chunk
