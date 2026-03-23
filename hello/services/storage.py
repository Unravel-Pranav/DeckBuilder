from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
import asyncio

from .config import settings
import time
from hello.ml.logger import GLOBAL_LOGGER as logger



class S3UploadError(RuntimeError):
    """Raised when uploading to S3 fails."""

def _build_boto_kwargs() -> dict[str, Any]:
    # In test, use explicit/dummy credentials for isolation.
    # if settings.env != "test":
    #     return {}
    # else:
    return {
        k: v
        for k, v in {
            "aws_access_key_id": settings.aws_access_key_id,
            "aws_secret_access_key": settings.aws_secret_access_key,
            # "aws_session_token": settings.aws_session_token,
            "region_name": settings.aws_region
        }.items()
        if v
    }




def _get_s3_client():  # pragma: no cover - thin wrapper
    if not settings.aws_bucket:
        return None
    try:
        import boto3  # type: ignore

        return boto3.client("s3", **_build_boto_kwargs())
    except Exception:  # pragma: no cover - boto3 import/config failure
        logger.exception("Failed to create S3 client")
        return None


def _upload_with_retry(client, *, bucket: str, key: str, body: bytes, content_type: str | None = None, attempts: int = 3, base_delay: float = 0.4) -> None:
    """Best-effort retry around S3 put_object to handle transient network issues.

    Raises S3UploadError if all attempts fail.
    """
    last_err: Exception | None = None
    for i in range(1, max(1, attempts) + 1):
        try:
            kwargs = {"Bucket": bucket, "Key": key, "Body": body}
            if content_type:
                kwargs["ContentType"] = content_type
            client.put_object(**kwargs)  # type: ignore[arg-type]
            return
        except Exception as exc:  # pragma: no cover - network dependent
            last_err = exc
            # Jittered backoff
            delay = base_delay * (2 ** (i - 1))
            try:
                time.sleep(delay)
            except Exception:
                pass
    raise S3UploadError(f"Failed to upload to s3://{bucket}/{key}") from last_err


async def save_report_to_s3(content: bytes, key_prefix: str = "reports/", *, filename: str | None = None, content_type: str | None = None) -> str:
    """Store report bytes to S3. If boto3/config not available, return a dummy path for dev mode.
    
    Raises:
        Exception: If S3 upload fails (when S3 is configured)
    """
    if filename:
        # Use provided filename, ensuring it has .pptx extension
        if not filename.endswith('.pptx'):
            filename = f"{filename}.pptx"
        key = f"{key_prefix}{filename}"
    else:
        # Use UUID if no filename provided
        key = f"{key_prefix}{uuid.uuid4()}.pptx"
    
    client = _get_s3_client()
    if not client or not settings.aws_bucket:
        # Fail loudly outside of test to avoid silent data loss
        env = (getattr(settings, "env", "") or "").lower()
        if env not in {"test"}:
            raise RuntimeError("S3 is not configured; cannot save report")
        logger.warning("S3 not configured; returning dummy path for key: %s", key)
        return f"s3://DUMMY-BUCKET/{key}"
    
    # S3 is configured - actual upload attempt
    try:
        await asyncio.to_thread(
            _upload_with_retry,
            client,
            bucket=settings.aws_bucket,
            key=key,
            body=content,
            content_type=content_type,
        )
        return f"s3://{settings.aws_bucket}/{key}"
    except Exception as e:
        logger.exception("Failed to upload report to S3", extra={"key": key})
        # CRITICAL: Raise exception so caller knows upload failed
        # Don't store invalid dummy path in database
        raise RuntimeError(f"S3 upload failed for key {key}") from e


async def upload_template_file_to_s3(
    content: bytes,
    filename: str,
    key_prefix: str = "templates/",
) -> str:
    """Upload a template PPT/PPTX file to S3 and return the object key."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".ppt", ".pptx"}:
        suffix = ".pptx"
    key = f"{key_prefix}{uuid.uuid4()}{suffix}"
    client = _get_s3_client()
    if not client or not settings.aws_bucket:
        logger.warning(
            "S3 client unavailable or bucket unset; upload aborted",
            extra={"key_prefix": key_prefix},
        )
        raise S3UploadError("S3 client unavailable")
    content_type = (
        "application/vnd.ms-powerpoint"
        if suffix == ".ppt"
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    try:
        await asyncio.to_thread(
            _upload_with_retry,
            client,
            bucket=settings.aws_bucket,
            key=key,
            body=content,
            content_type=content_type,
        )
        return key
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("Failed to upload template file", extra={"key": key})
        raise S3UploadError("Failed to upload template file") from exc


async def generate_presigned_url_for_key(
    key: str,
    expires_in: int = 7 * 24 * 60 * 60,
) -> str | None:
    client = _get_s3_client()
    if not client or not settings.aws_bucket:
        logger.warning(
            "Cannot generate presigned URL without S3 client/bucket", extra={"key": key}
        )
        return None
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.aws_bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception:
        logger.exception("Failed to generate presigned URL", extra={"key": key})
        return None
