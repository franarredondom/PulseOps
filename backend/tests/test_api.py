import os
from pathlib import Path
import asyncio

import pytest

TEST_DATABASE = Path(__file__).with_name("pulseops-test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["CRON_SECRET"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.checker import ProbeResult, ensure_public_target  # noqa: E402
from app.models import ServiceStatus  # noqa: E402


def test_monitor_lifecycle() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"

        created = client.post(
            "/api/monitors",
            json={"name": "Example API", "url": "https://example.com/health"},
        )
        assert created.status_code == 201
        monitor = created.json()
        assert monitor["status"] == "unknown"

        listed = client.get("/api/monitors")
        assert listed.status_code == 200
        assert any(item["id"] == monitor["id"] for item in listed.json())

        paused = client.patch(f"/api/monitors/{monitor['id']}", json={"is_active": False})
        assert paused.json()["status"] == "paused"

        deleted = client.delete(f"/api/monitors/{monitor['id']}")
        assert deleted.status_code == 204


def test_scheduler_requires_secret() -> None:
    with TestClient(app) as client:
        assert client.post("/api/checks/run").status_code == 401


def test_real_data_endpoints_start_empty() -> None:
    with TestClient(app) as client:
        overview = client.get("/api/overview")
        assert overview.status_code == 200
        assert overview.json()["totalChecks"] == 0
        assert overview.json()["availabilityPercent"] is None
        assert client.get("/api/checks/recent").json() == []
        assert client.get("/api/incidents").json() == []


def test_private_network_targets_are_rejected() -> None:
    with pytest.raises(ValueError, match="Private or reserved"):
        asyncio.run(ensure_public_target("http://127.0.0.1/health"))


def test_analyze_persists_a_real_check(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_probe(*_: object) -> ProbeResult:
        return ProbeResult(ServiceStatus.OPERATIONAL, 200, 42.5)

    monkeypatch.setattr("app.checker.probe", fake_probe)
    with TestClient(app) as client:
        analyzed = client.post(
            "/api/analyze",
            json={"name": "PulseOps test", "url": "https://example.com/health"},
        )
        assert analyzed.status_code == 200
        payload = analyzed.json()
        assert payload["monitor"]["status"] == "operational"
        assert payload["check"]["status_code"] == 200
        assert payload["check"]["latency_ms"] == 42.5

        recent = client.get("/api/checks/recent").json()
        assert recent[0]["monitor_name"] == "PulseOps test"
        assert client.get("/api/overview").json()["availabilityPercent"] == 100.0

        assert client.delete(f"/api/monitors/{payload['monitor']['id']}").status_code == 204
