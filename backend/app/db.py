from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db() -> dict:
    with engine.connect() as conn:
        version = conn.execute(text("SELECT PostGIS_Version()")).scalar()
        return {"database": "ok", "postgis": version}


# Read-only engine for the SQL playground (role berlin_ro, created by migration 0009).
engine_ro = create_engine(settings.database_url_ro, pool_pre_ping=True)
SessionRO = sessionmaker(bind=engine_ro, autoflush=False, autocommit=False)


def get_db_ro() -> Generator[Session, None, None]:
    db = SessionRO()
    try:
        yield db
    finally:
        db.close()
