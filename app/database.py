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
