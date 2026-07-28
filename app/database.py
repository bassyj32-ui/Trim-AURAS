from sqlmodel import SQLModel, create_engine

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=(settings.app_env == "development"),
)


def init_db():
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
    SQLModel.metadata.create_all(engine)


def force_db_sync():
    """Force a full WAL checkpoint so other processes see committed data immediately.

    Must be called *after* a session.commit() when other containers (e.g. Modal
    worker functions) need to read the same SQLite file from a shared Volume.
    """
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE);")
