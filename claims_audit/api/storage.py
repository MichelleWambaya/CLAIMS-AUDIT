"""
Object storage for generated reports.

Two backends:
- "local" (default): writes under settings.LOCAL_STORAGE_DIR, a Docker
  volume mounted into the app container. This is what makes the platform
  genuinely self-contained — no external storage account required to run
  it end to end.
- "s3": any S3-compatible endpoint (AWS S3, Cloudflare R2, MinIO, ...),
  for the cloud-deploy path where a persistent local volume may not be
  desirable.

Both implementations return a `storage_key` that `retrieve()` can turn
back into bytes — callers (the reports router) never need to know which
backend is active.
"""
import os
import shutil

from api.config import settings


def save_file(local_path: str, key: str) -> str:
    if settings.STORAGE_BACKEND == "s3":
        return _s3_save(local_path, key)
    return _local_save(local_path, key)


def retrieve_path(key: str) -> str:
    """Return a local filesystem path to the object's bytes. For the local
    backend this is direct; for S3 it downloads to a temp file first."""
    if settings.STORAGE_BACKEND == "s3":
        return _s3_download_to_temp(key)
    return _local_path(key)


def _local_path(key: str) -> str:
    return os.path.join(settings.LOCAL_STORAGE_DIR, key)


def _local_save(local_path: str, key: str) -> str:
    dest = _local_path(key)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(local_path, dest)
    return key


def _s3_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT or None,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


def _s3_save(local_path: str, key: str) -> str:
    client = _s3_client()
    client.upload_file(local_path, settings.S3_BUCKET, key)
    return key


def _s3_download_to_temp(key: str) -> str:
    import tempfile
    client = _s3_client()
    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(key)[1])
    os.close(fd)
    client.download_file(settings.S3_BUCKET, key, tmp_path)
    return tmp_path
