from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceStatus(StrEnum):
    UNKNOWN = "unknown"
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    DOWN = "down"
    PAUSED = "paused"


class IncidentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(Text)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=8)
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    latency_threshold_ms: Mapped[int] = mapped_column(Integer, default=750)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default=ServiceStatus.UNKNOWN)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    checks: Mapped[list["CheckResult"]] = relationship(back_populates="monitor", cascade="all, delete-orphan")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="monitor", cascade="all, delete-orphan")


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (Index("ix_check_results_monitor_checked", "monitor_id", "checked_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    monitor_id: Mapped[str] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    monitor: Mapped[Monitor] = relationship(back_populates="checks")


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_monitor_status", "monitor_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    monitor_id: Mapped[str] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(20), default=IncidentStatus.OPEN)
    cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    monitor: Mapped[Monitor] = relationship(back_populates="incidents")


class WebsiteAudit(Base):
    __tablename__ = "website_audits"
    __table_args__ = (Index("ix_website_audits_created", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text)
    hostname: Mapped[str] = mapped_column(String(255))
    status_code: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[float] = mapped_column(Float)
    size_bytes: Mapped[int] = mapped_column(Integer)
    overall_score: Mapped[int] = mapped_column(Integer)
    performance_score: Mapped[int] = mapped_column(Integer)
    seo_score: Mapped[int] = mapped_column(Integer)
    accessibility_score: Mapped[int] = mapped_column(Integer)
    security_score: Mapped[int] = mapped_column(Integer)
    report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
