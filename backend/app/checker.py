import asyncio
from dataclasses import dataclass
from ipaddress import ip_address
import socket
from time import perf_counter
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import CheckResult, Incident, IncidentStatus, Monitor, ServiceStatus, utc_now


@dataclass(frozen=True)
class ProbeResult:
    status: ServiceStatus
    status_code: int | None
    latency_ms: float | None
    error: str | None = None


async def ensure_public_target(raw_url: str) -> None:
    hostname = urlparse(raw_url).hostname
    if not hostname:
        raise ValueError("The URL does not include a valid hostname")

    addresses = await asyncio.to_thread(
        socket.getaddrinfo,
        hostname,
        None,
        type=socket.SOCK_STREAM,
    )
    if not addresses:
        raise ValueError("The hostname could not be resolved")

    for address_info in addresses:
        address = ip_address(address_info[4][0])
        if not address.is_global:
            raise ValueError("Private or reserved network targets are not allowed")


async def probe(monitor: Monitor) -> ProbeResult:
    started = perf_counter()
    try:
        await ensure_public_target(monitor.url)
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=monitor.timeout_seconds,
            headers={"User-Agent": "PulseOps/0.1 (+https://github.com/)"},
        ) as client:
            response = await client.get(monitor.url)
        latency = round((perf_counter() - started) * 1000, 2)
        if response.status_code != monitor.expected_status:
            return ProbeResult(ServiceStatus.DOWN, response.status_code, latency, f"Expected {monitor.expected_status}")
        status = ServiceStatus.DEGRADED if latency > monitor.latency_threshold_ms else ServiceStatus.OPERATIONAL
        return ProbeResult(status, response.status_code, latency)
    except httpx.TimeoutException:
        return ProbeResult(ServiceStatus.DOWN, None, None, "Request timed out")
    except httpx.HTTPError as error:
        return ProbeResult(ServiceStatus.DOWN, None, None, str(error)[:300])
    except (OSError, ValueError) as error:
        return ProbeResult(ServiceStatus.DOWN, None, None, str(error)[:300])


def persist_result(session: Session, monitor: Monitor, result: ProbeResult) -> CheckResult:
    settings = get_settings()
    now = utc_now()
    check = CheckResult(
        monitor_id=monitor.id,
        status=result.status,
        status_code=result.status_code,
        latency_ms=result.latency_ms,
        error=result.error,
        checked_at=now,
    )
    session.add(check)
    monitor.last_checked_at = now
    monitor.last_latency_ms = result.latency_ms
    monitor.status = result.status
    monitor.consecutive_failures = monitor.consecutive_failures + 1 if result.status == ServiceStatus.DOWN else 0

    open_incident = session.scalar(
        select(Incident).where(
            Incident.monitor_id == monitor.id,
            Incident.status == IncidentStatus.OPEN,
        )
    )
    if monitor.consecutive_failures >= settings.failure_threshold and open_incident is None:
        session.add(
            Incident(
                monitor_id=monitor.id,
                title=f"{monitor.name} no está respondiendo",
                cause=result.error or f"HTTP {result.status_code}",
            )
        )
    elif result.status in {ServiceStatus.OPERATIONAL, ServiceStatus.DEGRADED} and open_incident:
        open_incident.status = IncidentStatus.RESOLVED
        open_incident.resolved_at = now

    session.commit()
    session.refresh(check)
    return check


async def check_one(session: Session, monitor: Monitor) -> CheckResult:
    result = await probe(monitor)
    return persist_result(session, monitor, result)


async def check_many(monitors: list[Monitor]) -> list[tuple[str, ProbeResult]]:
    semaphore = asyncio.Semaphore(10)

    async def limited(monitor: Monitor) -> tuple[str, ProbeResult]:
        async with semaphore:
            return monitor.id, await probe(monitor)

    return await asyncio.gather(*(limited(monitor) for monitor in monitors))
