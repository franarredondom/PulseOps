from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .checker import check_many, check_one, persist_result
from .config import get_settings
from .database import Base, engine, get_session
from .models import CheckResult, Incident, IncidentStatus, Monitor, ServiceStatus, utc_now
from .schemas import (
    AnalysisRead,
    AnalyzeRequest,
    CheckRead,
    IncidentRead,
    MonitorCreate,
    MonitorRead,
    MonitorUpdate,
    RecentCheckRead,
    RunSummary,
)

SessionDep = Annotated[Session, Depends(get_session)]
MAX_MONITORS = 10


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            for table in ("monitors", "check_results", "incidents"):
                connection.execute(text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
    yield


app = FastAPI(
    title="PulseOps API",
    description="API de monitoreo HTTP, comprobaciones concurrentes e incidentes automáticos.",
    version="0.1.0",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Cron-Secret"],
)


@app.get("/health", tags=["system"])
def health(session: SessionDep) -> dict[str, str]:
    session.execute(select(1))
    return {"status": "ok", "database": "connected"}


@app.get("/api/monitors", response_model=list[MonitorRead], tags=["monitors"])
def list_monitors(session: SessionDep) -> list[Monitor]:
    return list(session.scalars(select(Monitor).order_by(Monitor.created_at.desc())))


@app.post("/api/monitors", response_model=MonitorRead, status_code=status.HTTP_201_CREATED, tags=["monitors"])
def create_monitor(payload: MonitorCreate, session: SessionDep) -> Monitor:
    total = session.scalar(select(func.count()).select_from(Monitor)) or 0
    if total >= MAX_MONITORS:
        raise HTTPException(status_code=409, detail=f"The free workspace supports up to {MAX_MONITORS} monitors")
    monitor = Monitor(**payload.model_dump(mode="json"))
    session.add(monitor)
    session.commit()
    session.refresh(monitor)
    return monitor


@app.post("/api/analyze", response_model=AnalysisRead, tags=["checks"])
async def analyze_url(payload: AnalyzeRequest, session: SessionDep) -> AnalysisRead:
    normalized_url = str(payload.url)
    monitor = session.scalar(select(Monitor).where(Monitor.url == normalized_url))
    if monitor is None:
        total = session.scalar(select(func.count()).select_from(Monitor)) or 0
        if total >= MAX_MONITORS:
            raise HTTPException(status_code=409, detail=f"The free workspace supports up to {MAX_MONITORS} monitors")
        hostname = urlparse(normalized_url).hostname or "Nuevo servicio"
        monitor = Monitor(
            name=payload.name or hostname,
            url=normalized_url,
            timeout_seconds=payload.timeout_seconds,
            expected_status=payload.expected_status,
            latency_threshold_ms=payload.latency_threshold_ms,
        )
        session.add(monitor)
        session.commit()
        session.refresh(monitor)

    check = await check_one(session, monitor)
    session.refresh(monitor)
    return AnalysisRead(
        monitor=MonitorRead.model_validate(monitor),
        check=CheckRead.model_validate(check),
    )


@app.patch("/api/monitors/{monitor_id}", response_model=MonitorRead, tags=["monitors"])
def update_monitor(monitor_id: str, payload: MonitorUpdate, session: SessionDep) -> Monitor:
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(monitor, field, value)
    if payload.is_active is False:
        monitor.status = ServiceStatus.PAUSED
    elif payload.is_active is True and monitor.status == ServiceStatus.PAUSED:
        monitor.status = ServiceStatus.UNKNOWN
    session.commit()
    session.refresh(monitor)
    return monitor


@app.delete("/api/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["monitors"])
def delete_monitor(monitor_id: str, session: SessionDep) -> Response:
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    session.delete(monitor)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/monitors/{monitor_id}/check", response_model=CheckRead, tags=["checks"])
async def run_single_check(monitor_id: str, session: SessionDep) -> CheckResult:
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    if not monitor.is_active:
        raise HTTPException(status_code=409, detail="Monitor is paused")
    return await check_one(session, monitor)


@app.post("/api/checks/run", response_model=RunSummary, tags=["checks"])
async def run_due_checks(
    session: SessionDep,
    x_cron_secret: Annotated[str | None, Header()] = None,
) -> RunSummary:
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Invalid scheduler secret")

    now = utc_now()
    active = list(session.scalars(select(Monitor).where(Monitor.is_active.is_(True))))
    due = [
        monitor
        for monitor in active
        if monitor.last_checked_at is None
        or monitor.last_checked_at + timedelta(minutes=monitor.interval_minutes) <= now
    ]
    results = await check_many(due)
    by_id = {monitor.id: monitor for monitor in due}
    for monitor_id, result in results:
        persist_result(session, by_id[monitor_id], result)

    counts = {state: 0 for state in (ServiceStatus.OPERATIONAL, ServiceStatus.DEGRADED, ServiceStatus.DOWN)}
    for _, result in results:
        counts[result.status] += 1
    return RunSummary(
        checked=len(results),
        operational=counts[ServiceStatus.OPERATIONAL],
        degraded=counts[ServiceStatus.DEGRADED],
        down=counts[ServiceStatus.DOWN],
    )


@app.get("/api/incidents", response_model=list[IncidentRead], tags=["incidents"])
def list_incidents(session: SessionDep, open_only: bool = False) -> list[IncidentRead]:
    query = (
        select(Incident, Monitor.name, Monitor.url)
        .join(Monitor, Incident.monitor_id == Monitor.id)
        .order_by(Incident.started_at.desc())
    )
    if open_only:
        query = query.where(Incident.status == IncidentStatus.OPEN)
    return [
        IncidentRead(
            id=incident.id,
            monitor_id=incident.monitor_id,
            monitor_name=monitor_name,
            monitor_url=monitor_url,
            title=incident.title,
            status=incident.status,
            cause=incident.cause,
            started_at=incident.started_at,
            resolved_at=incident.resolved_at,
        )
        for incident, monitor_name, monitor_url in session.execute(query).all()
    ]


@app.get("/api/checks/recent", response_model=list[RecentCheckRead], tags=["checks"])
def recent_checks(session: SessionDep, limit: int = 50) -> list[RecentCheckRead]:
    safe_limit = min(max(limit, 1), 200)
    rows = session.execute(
        select(CheckResult, Monitor.name, Monitor.url)
        .join(Monitor, CheckResult.monitor_id == Monitor.id)
        .order_by(CheckResult.checked_at.desc())
        .limit(safe_limit)
    ).all()
    return [
        RecentCheckRead(
            id=check.id,
            monitor_id=check.monitor_id,
            monitor_name=monitor_name,
            monitor_url=monitor_url,
            status=check.status,
            status_code=check.status_code,
            latency_ms=check.latency_ms,
            error=check.error,
            checked_at=check.checked_at,
        )
        for check, monitor_name, monitor_url in rows
    ]


@app.get("/api/overview", tags=["overview"])
def overview(session: SessionDep) -> dict[str, object]:
    total = session.scalar(select(func.count()).select_from(Monitor)) or 0
    active = session.scalar(select(func.count()).select_from(Monitor).where(Monitor.is_active.is_(True))) or 0
    incidents = session.scalar(select(func.count()).select_from(Incident).where(Incident.status == IncidentStatus.OPEN)) or 0
    average_latency = session.scalar(select(func.avg(CheckResult.latency_ms)).where(CheckResult.latency_ms.is_not(None)))
    total_checks = session.scalar(select(func.count()).select_from(CheckResult)) or 0
    healthy_checks = session.scalar(
        select(func.count()).select_from(CheckResult).where(
            CheckResult.status.in_([ServiceStatus.OPERATIONAL, ServiceStatus.DEGRADED])
        )
    ) or 0
    status_counts = {status.value: 0 for status in ServiceStatus}
    for monitor_status, count in session.execute(
        select(Monitor.status, func.count()).group_by(Monitor.status)
    ).all():
        status_counts[str(monitor_status)] = count
    return {
        "monitors": total,
        "activeMonitors": active,
        "openIncidents": incidents,
        "averageLatencyMs": round(float(average_latency), 2) if average_latency is not None else None,
        "availabilityPercent": round((healthy_checks / total_checks) * 100, 2) if total_checks else None,
        "totalChecks": total_checks,
        "statusCounts": status_counts,
    }
