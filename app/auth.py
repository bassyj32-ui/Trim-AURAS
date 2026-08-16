"""Supabase Auth gate for the FastAPI backend.

Every protected /api route depends on ``get_current_user``. The frontend
sends the Supabase session JWT in the ``Authorization: Bearer <token>``
header; here we verify it against Supabase Auth (server-side validation,
so revoked/expired sessions are rejected) and return the user identity.

The DB connection itself (Supabase Postgres via the pooler) is made with
the postgres superuser role, so row-level security does NOT apply to the
backend — this dependency is the real access gate.
"""

from typing import Optional

from fastapi import Header, HTTPException

from app.config import settings

_client = None


def _supabase():
    """Lazily build the Supabase client (anon key is frontend-safe)."""
    global _client
    if _client is None:
        if not settings.supabase_url or not settings.supabase_anon_key:
            raise HTTPException(
                503,
                "Auth is not configured — set SUPABASE_URL and SUPABASE_ANON_KEY",
            )
        from supabase import create_client

        _client = create_client(settings.supabase_url, settings.supabase_anon_key)
    return _client


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """Validate the Supabase JWT and return {id, email, metadata}.

    Raises 401 for missing/expired/invalid tokens so the frontend can
    prompt the user to sign in again.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            401, "Missing bearer token", headers={"WWW-Authenticate": "Bearer"}
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            401, "Missing bearer token", headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        user = _supabase().auth.get_user(token).user
    except Exception:
        raise HTTPException(
            401,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user:
        raise HTTPException(
            401,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "id": str(user.id),
        "email": user.email,
        "metadata": user.user_metadata or {},
    }
