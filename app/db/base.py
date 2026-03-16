from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, echo=False, future=True)


def get_session_maker() -> sessionmaker[Session]:
    engine = get_engine()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    session_local = get_session_maker()
    db = session_local()
    try:
        yield db
    finally:
        db.close()

