"""SQLAlchemy database configuration and FastAPI session dependency."""

import os
from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _get_database_url() -> str:
    """Return the configured database URL or fail before accepting traffic."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable must be configured.")
    return database_url


DATABASE_URL = _get_database_url()
engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


def get_db() -> Generator[Session, None, None]:
    """Yield one database session and close it after the request completes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
