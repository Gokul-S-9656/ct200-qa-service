"""
SQLAlchemy engine + session factory for the relational store.

The document tree (Node) and Selections live here because they are
structurally rigid and relational by nature: a node has exactly one parent,
a fixed set of typed columns, and selections reference nodes by foreign key.
That's precisely what a relational database is good at enforcing.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def dispose_engine() -> None:
    """
    Close every pooled connection and release the underlying file handle.

    Matters most on Windows: SQLite there holds an OS-level lock on the
    db file for as long as any connection in the pool is open, and
    unlike POSIX, Windows won't let you delete (or even reopen) a file
    that's still locked. On Linux/macOS this is a no-op you'd never
    notice; on Windows, skipping it is exactly what causes
    `PermissionError: [WinError 32] ... being used by another process`
    when something downstream (a test teardown, a redeploy script) tries
    to remove or replace the db file right after the app shuts down.
    """
    engine.dispose()
