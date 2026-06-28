"""PostgreSQL connection helpers for the investment workspace."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


class PortfolioDatabaseUnavailable(RuntimeError):
    """Raised when the investment workspace database is not configured."""


_ENGINE = None
_SESSIONMAKER = None
_INITIALIZED = False


def database_url() -> str | None:
    return os.getenv("DATABASE_URL") or os.getenv("VIBE_DATABASE_URL")


def _load_sqlalchemy():
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
    except ImportError as exc:
        raise PortfolioDatabaseUnavailable(
            "Investment workspace requires SQLAlchemy and psycopg. Install project dependencies first."
        ) from exc
    return create_engine, sessionmaker


def engine():
    global _ENGINE, _SESSIONMAKER
    url = database_url()
    if not url:
        raise PortfolioDatabaseUnavailable("DATABASE_URL or VIBE_DATABASE_URL is not configured.")
    if _ENGINE is None:
        create_engine, sessionmaker = _load_sqlalchemy()
        _ENGINE = create_engine(url, pool_pre_ping=True, future=True)
        _SESSIONMAKER = sessionmaker(bind=_ENGINE, autoflush=False, expire_on_commit=False, future=True)
    return _ENGINE


def init_db() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    from .models import Base

    Base.metadata.create_all(engine())
    _INITIALIZED = True


@contextmanager
def session_scope() -> Iterator[object]:
    init_db()
    if _SESSIONMAKER is None:
        engine()
    session = _SESSIONMAKER()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
