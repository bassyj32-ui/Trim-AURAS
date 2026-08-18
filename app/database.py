from sqlmodel import SQLModel, Session, create_engine

from app.config import MODAL, settings

# On Modal we connect via Supabase's shared Supavisor pooler
# (aws-0-*-pooler.supabase.com) which is IPv4-compatible, avoiding
# the IPv6 routing issue that plagues the direct db.xxxx.supabase.co
# endpoint from Modal's network.
_connect_args = {
    "connect_timeout": 10,           # fail fast if unreachable
    "sslmode": "require",            # Supabase always needs SSL
    "gssencmode": "disable",         # no GSSAPI on Supabase
}

if MODAL:
    # The shared pooler uses a different hostname and port.
    # The .env / secret already has the correct URL for the pooler
    # (postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-eu-west-1.pooler.supabase.com:6543/postgres)
    # so nothing extra to do here — just make sure the URL is used as-is.
    pass

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=(settings.app_env == "development"),
)


def get_session():
    with Session(engine) as session:
        yield session


def init_db():
    """Ensure all tables exist.

    In production (Modal), tables are created via migration.  This call is a
    safety net for local dev so SQLModel metadata creates what's missing.
    """
    try:
        SQLModel.metadata.create_all(engine)
    except Exception as exc:
        import warnings
        warnings.warn(f"init_db: could not create tables — {exc}")
