from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    connection_args = {"check_same_thread": False} if (url or get_settings().database_url).startswith("sqlite") else {}
    return create_engine(url or get_settings().database_url, pool_pre_ping=True, connect_args=connection_args)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

