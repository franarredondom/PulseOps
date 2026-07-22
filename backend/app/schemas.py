from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class MonitorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    url: HttpUrl
    interval_minutes: int = Field(default=5, ge=1, le=1440)
    timeout_seconds: int = Field(default=8, ge=1, le=30)
    expected_status: int = Field(default=200, ge=100, le=599)
    latency_threshold_ms: int = Field(default=750, ge=50, le=30_000)


class MonitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    latency_threshold_ms: int | None = Field(default=None, ge=50, le=30_000)
    is_active: bool | None = None


class MonitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str
    interval_minutes: int
    timeout_seconds: int
    is_active: bool
    status: str
    consecutive_failures: int
    last_latency_ms: float | None
    last_checked_at: datetime | None
    created_at: datetime


class CheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    monitor_id: str
    status: str
    status_code: int | None
    latency_ms: float | None
    error: str | None
    checked_at: datetime


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    monitor_id: str
    title: str
    status: str
    cause: str | None
    started_at: datetime
    resolved_at: datetime | None


class RunSummary(BaseModel):
    checked: int
    operational: int
    degraded: int
    down: int
