"""
Link-based sync — a substitute for the full OneDrive Graph API connector
for cases where registering an Azure app / getting admin consent isn't
available. Instead of Drive ID + folder path + OAuth, this just fetches
a shared file URL directly over HTTP.

Requires the file's sharing permission to be "Anyone with the link can
view" (or otherwise fetchable without an interactive Microsoft login) —
if an organization's policy blocks that kind of sharing, this will get
back an HTML sign-in page instead of the file, which is detected and
reported clearly rather than silently mis-parsed as data.

"Sync" here means on-demand re-fetch (click the button, pulls the current
version of the file again) rather than a scheduled background job — there
is no cron/webhook trigger wired up, since that's meaningfully more
infrastructure (a queue + scheduler) than fits this narrower need.
"""
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import User
from auth.security import get_current_user
from api.ingest_common import parse_and_merge

router = APIRouter(prefix="/sessions/{session_id}/link-sync", tags=["link-sync"])


class LinkSyncRequest(BaseModel):
    file_url: str
    sheet: str | None = None


def _coerce_direct_download_url(url: str) -> str:
    """
    OneDrive/SharePoint share links usually render an HTML preview page by
    default. Appending download=1 to the query string requests the raw
    file bytes instead, for both onedrive.live.com and SharePoint-hosted
    links. If the URL already has that param, leave it alone.
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "download" not in query:
        query["download"] = ["1"]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _guess_filename(url: str, content_disposition: str | None) -> str:
    if content_disposition:
        match = re.search(r'filename\*?="?([^";]+)"?', content_disposition)
        if match:
            return match.group(1)
    path = urlparse(url).path
    return path.rsplit("/", 1)[-1] or "downloaded_file"


@router.post("")
def link_sync(
    session_id: str,
    body: LinkSyncRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fetch_url = _coerce_direct_download_url(body.file_url)

    try:
        resp = requests.get(fetch_url, allow_redirects=True, timeout=60)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach that link: {exc}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"The link returned HTTP {resp.status_code} — it may require sign-in "
                   f"or the sharing permission may not be set to \"Anyone with the link.\"",
        )

    content_type = resp.headers.get("content-type", "")
    if "text/html" in content_type:
        raise HTTPException(
            status_code=422,
            detail="That link returned a webpage instead of a file — this usually means it "
                   "requires signing in to Microsoft first, which this endpoint can't do. "
                   "Check the file's sharing settings are set to \"Anyone with the link.\"",
        )

    filename = _guess_filename(body.file_url, resp.headers.get("content-disposition"))
    if not filename.lower().endswith((".csv", ".xlsx", ".xlsm", ".xls")):
        # best-effort guess from content-type if the URL/header didn't carry an extension
        filename += ".xlsx" if "spreadsheet" in content_type else ".csv"

    return parse_and_merge(
        session_id=session_id,
        filename=filename,
        contents=resp.content,
        sheet=body.sheet,
        source_type="link_sync",
        source_ref=body.file_url,
        db=db,
    )
