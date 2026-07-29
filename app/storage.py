"""Cloudflare R2 storage helpers.

R2 is currently DISABLED (TLS cert not provisioned).
All clip storage falls back to the Modal Volume (or local tmp/).
Set ``config.R2_ENABLED = True`` once Cloudflare resolves the incident.
"""

import boto3
from botocore.config import Config as BotoConfig

from app.config import R2_ENABLED, settings

_r2_client = None


def _get_client():
    global _r2_client
    if _r2_client is None:
        _r2_client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=BotoConfig(
                signature_version="s3v4",
                region_name="us-east-1",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
            verify=settings.r2_verify_ssl,
        )
    return _r2_client


def upload_to_r2(file_path: str, key: str) -> str | None:
    """Upload a file to Cloudflare R2 and return its public URL.

    Returns ``None`` when R2 is disabled or the upload fails.
    """
    if not R2_ENABLED:
        return None

    try:
        client = _get_client()
        client.upload_file(
            file_path,
            settings.r2_bucket_name,
            key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        return f"{settings.r2_public_domain}/{key}"
    except Exception as e:
        print(f"[R2] Upload failed for {key} (non-fatal): {e}")
        return None


def generate_presigned_url(key: str, expires_in: int = 86400) -> str | None:
    """Generate a presigned download URL for a clip (valid 24h by default).

    Returns ``None`` when R2 is disabled or the request fails.
    """
    if not R2_ENABLED:
        return None

    try:
        client = _get_client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.r2_bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        print(f"[R2] Presigned URL failed for {key} (non-fatal): {e}")
        return None
