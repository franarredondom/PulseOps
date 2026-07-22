import os
from pathlib import Path

TEST_DATABASE = Path(__file__).with_name("pulseops-test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["CRON_SECRET"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


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
