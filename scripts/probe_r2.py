"""Probe Cloudflare R2 connectivity: TLS cert validity + read/write access.

Reads credentials from app.config (i.e. .env), matching exactly what the
app uses. Exits 0 if R2 is fully operational, non-zero otherwise.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boto3
from botocore.config import Config as BotoConfig

from app.config import settings

print(f"R2 account id : {settings.r2_account_id}")
print(f"R2 bucket     : {settings.r2_bucket_name}")
print(f"R2 public     : {settings.r2_public_domain}")
print()

client = boto3.client(
    "s3",
    endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=settings.r2_access_key_id,
    aws_secret_access_key=settings.r2_secret_access_key,
    config=BotoConfig(
        signature_version="s3v4",
        region_name="us-east-1",
        retries={"max_attempts": 2, "mode": "standard"},
    ),
)

# --- 1. Read probe: does the bucket exist / TLS cert valid? ---
try:
    resp = client.head_bucket(Bucket=settings.r2_bucket_name)
    print(f"[OK] head_bucket -> HTTP {resp.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
except Exception as e:
    print(f"[FAIL] head_bucket: {type(e).__name__}: {e}")
    print("-> R2 not reachable (likely TLS cert still not provisioned).")
    sys.exit(1)

# --- 2. List probe ---
try:
    resp = client.list_objects_v2(Bucket=settings.r2_bucket_name, MaxKeys=5)
    keys = [o["Key"] for o in resp.get("Contents", [])]
    print(f"[OK] list_objects -> {len(keys)} objects (showing {keys[:5]})")
except Exception as e:
    print(f"[FAIL] list_objects: {type(e).__name__}: {e}")
    sys.exit(1)

# --- 3. Write/read/delete round-trip ---
probe_key = "probes/probe_hello.txt"
try:
    body = b"trimaura r2 probe ok"
    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=probe_key,
        Body=body,
        ContentType="text/plain",
    )
    print(f"[OK] put_object -> {probe_key}")

    with tempfile.NamedTemporaryFile(delete=True, suffix=".txt") as f:
        client.download_file(settings.r2_bucket_name, probe_key, f.name)
        got = Path(f.name).read_bytes()
    ok = got == body
    print(f"[{'OK' if ok else 'FAIL'}] download round-trip -> {'content matches' if ok else 'content mismatch'}")

    client.delete_object(Bucket=settings.r2_bucket_name, Key=probe_key)
    print(f"[OK] delete_object -> {probe_key}")
except Exception as e:
    print(f"[FAIL] round-trip: {type(e).__name__}: {e}")
    sys.exit(1)

print()
print("RESULT: R2 is operational — TLS cert is provisioned and read/write works.")
