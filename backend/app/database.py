from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
if settings.database_url.startswith("sqlite"):
    engine_options = {"connect_args": {"check_same_thread": False}}
else:
    engine_options = {
        "connect_args": {"sslmode": "require"},
        "pool_size": 5,
        "max_overflow": 5,
        "pool_recycle": 300,
    }

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    **engine_options,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
