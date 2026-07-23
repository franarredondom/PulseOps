from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from .auditor import AuditError, audit_website
from .auth import AuthUser, get_current_user
from .checker import check_many, check_one, persist_result
from .config import get_settings
from .database import Base, engine, get_session
from .models import CheckResult, Incident, IncidentStatus, Monitor, ServiceStatus, WebsiteAudit, utc_now
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
    WebsiteAuditRead,
    WebsiteAuditRequest,
)

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]
MAX_MONITORS = 10


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        schema = "public." if engine.dialect.name == "postgresql" else ""
        database_inspector = inspect(connection)
        for table in ("monitors", "website_audits"):
            columns = {column["name"] for column in database_inspector.get_columns(table)}
            if "owner_id" not in columns:
                connection.execute(text(f"ALTER TABLE {schema}{table} ADD COLUMN owner_id VARCHAR(36)"))
            connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_id ON {schema}{table} (owner_id)"))
        connection.execute(text(f"UPDATE {schema}monitors SET is_active = false, status = 'paused' WHERE owner_id IS NULL AND is_active = true"))
        if engine.dialect.name == "postgresql":
            for table in ("monitors", "check_results", "incidents", "website_audits"):
                connection.execute(text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
    yield


app = FastAPI(
    title="PulseOps API",
    description="Auditoría técnica de sitios web y monitoreo HTTP con datos reales.",
    version="1.0.0",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Cron-Secret"],
)


@app.get("/health", tags=["system"])
def health(session: SessionDep) -> dict[str, str]:
    session.execute(select(1))
    return {"status": "ok", "database": "connected"}


@app.get("/api/account", tags=["account"])
def account(user: CurrentUserDep) -> dict[str, str]:
    return {"id": user.id, "email": user.email, "name": user.name}


@app.post("/api/audits", response_model=WebsiteAuditRead, status_code=status.HTTP_201_CREATED, tags=["audits"])
async def create_website_audit(payload: WebsiteAuditRequest, session: SessionDep, user: CurrentUserDep) -> WebsiteAudit:
    raw_url = str(payload.url)
    try:
        report = await audit_website(raw_url)
    except AuditError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    http = report["http"]
    scores = report["scores"]
    audit = WebsiteAudit(
        owner_id=user.id,
        url=raw_url,
        final_url=http["finalUrl"],
        hostname=urlparse(http["finalUrl"]).hostname or "unknown",
        status_code=http["statusCode"],
        latency_ms=http["latencyMs"],
        size_bytes=http["sizeBytes"],
        overall_score=scores["overall"],
        performance_score=scores["performance"],
        seo_score=scores["seo"],
        accessibility_score=scores["accessibility"],
        security_score=scores["security"],
        report=report,
    )
    session.add(audit)
    session.commit()
    session.refresh(audit)
    return audit


@app.get("/api/audits", response_model=list[WebsiteAuditRead], tags=["audits"])
def list_website_audits(session: SessionDep, user: CurrentUserDep, limit: int = 20) -> list[WebsiteAudit]:
    safe_limit = min(max(limit, 1), 100)
    return list(session.scalars(select(WebsiteAudit).where(WebsiteAudit.owner_id == user.id).order_by(WebsiteAudit.created_at.desc()).limit(safe_limit)))


@app.get("/api/audits/{audit_id}", response_model=WebsiteAuditRead, tags=["audits"])
def get_website_audit(audit_id: str, session: SessionDep, user: CurrentUserDep) -> WebsiteAudit:
    audit = session.scalar(select(WebsiteAudit).where(WebsiteAudit.id == audit_id, WebsiteAudit.owner_id == user.id))
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


@app.delete("/api/audits/{audit_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["audits"])
def delete_website_audit(audit_id: str, session: SessionDep, user: CurrentUserDep) -> Response:
    audit = session.scalar(select(WebsiteAudit).where(WebsiteAudit.id == audit_id, WebsiteAudit.owner_id == user.id))
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    session.delete(audit)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/monitors", response_model=list[MonitorRead], tags=["monitors"])
def list_monitors(session: SessionDep, user: CurrentUserDep) -> list[Monitor]:
    return list(session.scalars(select(Monitor).where(Monitor.owner_id == user.id).order_by(Monitor.created_at.desc())))


@app.post("/api/monitors", response_model=MonitorRead, status_code=status.HTTP_201_CREATED, tags=["monitors"])
def create_monitor(payload: MonitorCreate, session: SessionDep, user: CurrentUserDep) -> Monitor:
    total = session.scalar(select(func.count()).select_from(Monitor).where(Monitor.owner_id == user.id)) or 0
    if total >= MAX_MONITORS:
        raise HTTPException(status_code=409, detail=f"Tu cuenta admite hasta {MAX_MONITORS} monitores")
    monitor = Monitor(owner_id=user.id, **payload.model_dump(mode="json"))
    session.add(monitor)
    session.commit()
    session.refresh(monitor)
    return monitor


@app.post("/api/analyze", response_model=AnalysisRead, tags=["checks"])
async def analyze_url(payload: AnalyzeRequest, session: SessionDep, user: CurrentUserDep) -> AnalysisRead:
    normalized_url = str(payload.url)
    monitor = session.scalar(select(Monitor).where(Monitor.url == normalized_url, Monitor.owner_id == user.id))
    if monitor is None:
        total = session.scalar(select(func.count()).select_from(Monitor).where(Monitor.owner_id == user.id)) or 0
        if total >= MAX_MONITORS:
            raise HTTPException(status_code=409, detail=f"Tu cuenta admite hasta {MAX_MONITORS} monitores")
        hostname = urlparse(normalized_url).hostname or "Nuevo servicio"
        monitor = Monitor(
            owner_id=user.id,
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
def update_monitor(monitor_id: str, payload: MonitorUpdate, session: SessionDep, user: CurrentUserDep) -> Monitor:
    monitor = session.scalar(select(Monitor).where(Monitor.id == monitor_id, Monitor.owner_id == user.id))
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
def delete_monitor(monitor_id: str, session: SessionDep, user: CurrentUserDep) -> Response:
    monitor = session.scalar(select(Monitor).where(Monitor.id == monitor_id, Monitor.owner_id == user.id))
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    session.delete(monitor)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/monitors/{monitor_id}/check", response_model=CheckRead, tags=["checks"])
async def run_single_check(monitor_id: str, session: SessionDep, user: CurrentUserDep) -> CheckResult:
    monitor = session.scalar(select(Monitor).where(Monitor.id == monitor_id, Monitor.owner_id == user.id))
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
def list_incidents(session: SessionDep, user: CurrentUserDep, open_only: bool = False) -> list[IncidentRead]:
    query = (
        select(Incident, Monitor.name, Monitor.url)
        .join(Monitor, Incident.monitor_id == Monitor.id)
        .where(Monitor.owner_id == user.id)
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
def recent_checks(session: SessionDep, user: CurrentUserDep, limit: int = 50) -> list[RecentCheckRead]:
    safe_limit = min(max(limit, 1), 200)
    rows = session.execute(
        select(CheckResult, Monitor.name, Monitor.url)
        .join(Monitor, CheckResult.monitor_id == Monitor.id)
        .where(Monitor.owner_id == user.id)
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
def overview(session: SessionDep, user: CurrentUserDep) -> dict[str, object]:
    total = session.scalar(select(func.count()).select_from(Monitor).where(Monitor.owner_id == user.id)) or 0
    active = session.scalar(select(func.count()).select_from(Monitor).where(Monitor.owner_id == user.id, Monitor.is_active.is_(True))) or 0
    incidents = session.scalar(
        select(func.count()).select_from(Incident).join(Monitor, Incident.monitor_id == Monitor.id).where(
            Monitor.owner_id == user.id, Incident.status == IncidentStatus.OPEN
        )
    ) or 0
    average_latency = session.scalar(
        select(func.avg(CheckResult.latency_ms)).join(Monitor, CheckResult.monitor_id == Monitor.id).where(
            Monitor.owner_id == user.id, CheckResult.latency_ms.is_not(None)
        )
    )
    total_checks = session.scalar(
        select(func.count()).select_from(CheckResult).join(Monitor, CheckResult.monitor_id == Monitor.id).where(Monitor.owner_id == user.id)
    ) or 0
    healthy_checks = session.scalar(
        select(func.count()).select_from(CheckResult).join(Monitor, CheckResult.monitor_id == Monitor.id).where(
            Monitor.owner_id == user.id,
            CheckResult.status.in_([ServiceStatus.OPERATIONAL, ServiceStatus.DEGRADED])
        )
    ) or 0
    status_counts = {status.value: 0 for status in ServiceStatus}
    for monitor_status, count in session.execute(
        select(Monitor.status, func.count()).where(Monitor.owner_id == user.id).group_by(Monitor.status)
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
