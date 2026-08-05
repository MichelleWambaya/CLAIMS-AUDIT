"""
Link-based sync (ingestion path 3 of 3) — a substitute for the full
OneDrive Graph API connector for cases where registering an Azure app /
getting admin consent isn't available. Instead of Drive ID + folder path
+ OAuth, this just fetches a shared file URL directly over HTTPS.

Requires the file's sharing permission to be "Anyone with the link can
view" (or otherwise fetchable without an interactive Microsoft login) —
if an organization's policy blocks that kind of sharing, this gets back
an HTML sign-in page instead of the file, which is detected and reported
clearly rather than silently mis-parsed as data.

"Sync" here means on-demand re-fetch (click the button, pulls the current
version of the file again) rather than a scheduled background job — there
is no cron/webhook trigger wired up, since that's meaningfully more
infrastructure (a queue + scheduler) than fits this narrower need.

The HTTP download itself streams to the shared upload volume in bounded
chunks (never loads the whole response into memory) so this scales the
same way manual upload does for a large file.
"""
import os
import re
import tempfile
import uuid
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.models import User, SourceFile
from api.queue import default_queue
from api.jobs import run_upload_ingest_job
from api.ingest_common import sniff_excel_sheets
from auth.security import get_current_user

router = APIRouter(prefix="/sessions/{session_id}/link-sync", tags=["link-sync"])

_CHUNK_SIZE = 1024 * 1024


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
        resp = requests.get(fetch_url, allow_redirects=True, timeout=60, stream=True)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach that link: {exc}")

    if resp.status_code != 200:
        resp.close()
        raise HTTPException(
            status_code=502,
            detail=f"The link returned HTTP {resp.status_code} — it may require sign-in "
                   f"or the sharing permission may not be set to \"Anyone with the link.\"",
        )

    content_type = resp.headers.get("content-type", "")
    if "text/html" in content_type:
        resp.close()
        raise HTTPException(
            status_code=422,
            detail="That link returned a webpage instead of a file — this usually means it "
                   "requires signing in to Microsoft first, which this endpoint can't do. "
                   "Check the file's sharing settings are set to \"Anyone with the link.\"",
        )

    filename = _guess_filename(body.file_url, resp.headers.get("content-disposition"))
    if not filename.lower().endswith((".csv", ".xlsx", ".xlsm", ".xls")):
        filename += ".xlsx" if "spreadsheet" in content_type else ".csv"

    os.makedirs(settings.UPLOAD_TMP_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="claims_linksync_", suffix=os.path.splitext(filename)[1], dir=settings.UPLOAD_TMP_DIR
    )
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in resp.iter_content(chunk_size=_CHUNK_SIZE):
                if chunk:
                    out.write(chunk)
    finally:
        resp.close()

    is_excel = filename.lower().endswith((".xlsx", ".xlsm", ".xls"))
    sheet = body.sheet
    if is_excel and sheet is None:
        sheet_names = sniff_excel_sheets(tmp_path)
        if len(sheet_names) > 1:
            os.remove(tmp_path)
            return {"needs_sheet_selection": True, "sheets": sheet_names}
        sheet = sheet_names[0] if sheet_names else None
        if sheet is None:
            os.remove(tmp_path)
            raise HTTPException(status_code=422, detail="Workbook has no sheets.")

    source_file = SourceFile(
        id=uuid.uuid4(),
        audit_session_id=session_id,
        source_type="link_sync",
        source_ref=body.file_url,
        file_name=filename,
        sheet_name=sheet,
        status="pending",
    )
    db.add(source_file)
    db.commit()

    default_queue.enqueue(
        run_upload_ingest_job, str(source_file.id), session_id, filename, tmp_path, sheet,
        job_timeout="2h",
    )

    return {"source_file_id": str(source_file.id), "status": "queued"}
