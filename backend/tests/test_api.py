import os
from pathlib import Path
import asyncio

import pytest

TEST_DATABASE = Path(__file__).with_name("pulseops-test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["SUPABASE_PUBLISHABLE_KEY"] = "sb_publishable_test"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.auth import AuthUser, get_current_user  # noqa: E402
from app.checker import ProbeResult, ensure_public_target  # noqa: E402
from app.auditor import FetchedPage, build_report, looks_like_html  # noqa: E402
from app.models import ServiceStatus  # noqa: E402


TEST_USER = AuthUser(id="11111111-1111-1111-1111-111111111111", email="test@example.com", name="Test User")
app.dependency_overrides[get_current_user] = lambda: TEST_USER


def test_private_routes_require_a_session() -> None:
    override = app.dependency_overrides.pop(get_current_user)
    try:
        with TestClient(app) as client:
            response = client.get("/api/account")
            assert response.status_code == 401
            assert response.json()["detail"] == "Inicia sesión para continuar"
    finally:
        app.dependency_overrides[get_current_user] = override


def test_monitor_lifecycle() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/api/account").json()["email"] == "test@example.com"

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


def test_scheduler_requires_github_identity() -> None:
    with TestClient(app) as client:
        assert client.post("/api/checks/run").status_code == 401


def test_scheduler_accepts_verified_github_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.main.verify_github_actions_token",
        lambda _: {"repository": "franarredondom/PulseOps"},
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/checks/run",
            headers={"Authorization": "Bearer github-oidc-token"},
        )
        assert response.status_code == 200
        assert response.json()["checked"] == 0


def test_scheduler_rejects_invalid_github_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.github_oidc import GitHubOIDCError

    def reject(_: str) -> None:
        raise GitHubOIDCError("invalid")

    monkeypatch.setattr("app.main.verify_github_actions_token", reject)
    with TestClient(app) as client:
        response = client.post(
            "/api/checks/run",
            headers={"Authorization": "Bearer forged-token"},
        )
        assert response.status_code == 401


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


def test_audit_report_uses_real_html_signals() -> None:
    html = b"""<!doctype html><html lang="es"><head>
    <title>Una pagina preparada para buscadores</title>
    <meta name="description" content="Esta descripcion explica claramente el contenido de la pagina y tiene una longitud suficientemente util para buscadores y personas interesadas.">
    <meta name="viewport" content="width=device-width"><link rel="canonical" href="https://example.com/">
    <meta property="og:title" content="Example"><meta property="og:description" content="Description">
    </head><body><h1>Titulo principal</h1><img src="hero.jpg" alt="Equipo trabajando">
    <a href="/contacto">Contacto</a><a href="https://external.example">Referencia externa</a></body></html>"""
    report = build_report(
        FetchedPage(
            requested_url="https://example.com/",
            final_url="https://example.com/",
            status_code=200,
            latency_ms=120,
            body=html,
            headers={
                "content-type": "text/html; charset=utf-8",
                "content-encoding": "br",
                "strict-transport-security": "max-age=31536000",
                "content-security-policy": "default-src 'self'",
                "x-content-type-options": "nosniff",
                "x-frame-options": "DENY",
                "referrer-policy": "strict-origin",
                "permissions-policy": "camera=()",
            },
            redirects=[],
        ),
        robots_exists=True,
        sitemap_exists=True,
    )
    assert report["scores"]["overall"] >= 90
    assert report["page"]["h1Count"] == 1
    assert report["content"]["imagesWithAlt"] == 1
    assert report["content"]["internalLinks"] == 1
    assert report["content"]["externalLinks"] == 1


def test_html_sniffing_handles_incorrect_content_type() -> None:
    assert looks_like_html(b"\n\xef\xbb\xbf<!doctype html><html><head></head></html>")
    assert looks_like_html(b"<html lang='es'><body>Contenido</body></html>")
    assert not looks_like_html(b"local_rate_limited")
    assert not looks_like_html(b'{"status":"ok"}')


def test_audit_endpoint_persists_report(monkeypatch: pytest.MonkeyPatch) -> None:
    report = {
        "scores": {"overall": 80, "performance": 90, "seo": 80, "accessibility": 75, "security": 75},
        "page": {"title": "Example"},
        "http": {"finalUrl": "https://example.com/", "statusCode": 200, "latencyMs": 125.5, "sizeBytes": 2048},
        "seo": {}, "content": {}, "security": {}, "technologies": [], "recommendations": [], "scope": "test",
    }

    async def fake_audit(_: str) -> dict[str, object]:
        return report

    monkeypatch.setattr("app.main.audit_website", fake_audit)
    with TestClient(app) as client:
        created = client.post("/api/audits", json={"url": "https://example.com"})
        assert created.status_code == 201
        payload = created.json()
        assert payload["overall_score"] == 80
        assert payload["hostname"] == "example.com"
        assert client.get(f"/api/audits/{payload['id']}").status_code == 200
        assert any(item["id"] == payload["id"] for item in client.get("/api/audits").json())
        assert client.delete(f"/api/audits/{payload['id']}").status_code == 204


def test_users_cannot_see_each_others_monitors() -> None:
    with TestClient(app) as client:
        created = client.post("/api/monitors", json={"name": "Private service", "url": "https://example.com/private"})
        assert created.status_code == 201
        monitor_id = created.json()["id"]

        other_user = AuthUser(id="22222222-2222-2222-2222-222222222222", email="other@example.com", name="Other")
        app.dependency_overrides[get_current_user] = lambda: other_user
        try:
            assert client.get("/api/monitors").json() == []
            assert client.delete(f"/api/monitors/{monitor_id}").status_code == 404
        finally:
            app.dependency_overrides[get_current_user] = lambda: TEST_USER

        assert client.delete(f"/api/monitors/{monitor_id}").status_code == 204
