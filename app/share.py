"""Stateless public share tokens for clips.

A share link is ``/clip/{clip_id}?t=<token>``. The token is derived with
HMAC-SHA256 over the clip_id using a server-side secret, so:

* **No schema change / migration / backfill** — every existing clip is
  shareable the moment this ships (tokens are computed on demand).
* **Unguessable but public** (YouTube-"unlisted" model): anyone with the
  link can watch *and* download the clip; anyone without it gets 404. The
  token is the only secret (clip_ids are sequential ints), so it carries
  128 bits of keyed HMAC output.
* **Revocation is all-or-nothing** — rotate ``SHARE_SECRET`` and every
  share link dies at once. There is deliberately no per-clip revocation
  at this stage; revisit if you ever need it.

The ``ta1`` prefix version-tags the format so a future rotation can change
the derivation without invalidating old links it wants to keep.
"""

import hashlib
import hmac

from app.config import settings

# Insecure dev fallback so tests and local dev work without a configured
# secret. NEVER rely on this in production — the deployed app must set
# SHARE_SECRET (its token would otherwise be derivable from this constant).
_DEV_FALLBACK = b"insecure-dev-share-secret-change-me"

_PREFIX = "ta1"


def _secret() -> bytes:
    raw = settings.share_secret.strip()
    return raw.encode() if raw else _DEV_FALLBACK


def make_share_token(clip_id: int) -> str:
    """Build the share token for a clip."""
    digest = hmac.new(_secret(), str(clip_id).encode(), hashlib.sha256).digest()
    return f"{_PREFIX}{digest.hex()[:32]}"


def verify_share_token(clip_id: int, token: str | None) -> bool:
    """Constant-time check of a share token."""
    if not token:
        return False
    expected = make_share_token(clip_id)
    return hmac.compare_digest(expected, token)
