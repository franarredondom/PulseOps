from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: tuple[str, ...]
    cron_secret: str
    failure_threshold: int
    supabase_url: str
    supabase_publishable_key: str


@lru_cache
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "sqlite:///./pulseops.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    origins = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    )
    return Settings(
        database_url=database_url,
        cors_origins=origins,
        cron_secret=os.getenv("CRON_SECRET", "local-development-secret"),
        failure_threshold=max(1, int(os.getenv("FAILURE_THRESHOLD", "3"))),
        supabase_url=os.getenv("SUPABASE_URL", "https://kpfqzyejzcirlavewmqi.supabase.co").rstrip("/"),
        supabase_publishable_key=os.getenv(
            "SUPABASE_PUBLISHABLE_KEY",
            "sb_publishable_JYksltCemRN_zuY8ASF1ug_i5p_wXPl",
        ),
    )
