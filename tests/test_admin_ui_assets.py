import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import admin, availability, dashboard, photos


client = TestClient(app)


def test_shared_admin_css_served():
    response = client.get("/static/admin/surf-admin.css")
    assert response.status_code == 200
    assert "--sf-river" in response.text
    assert ".sf-app" in response.text


def test_shared_admin_js_served():
    response = client.get("/static/admin/surf-admin.js")
    assert response.status_code == 200
    assert "window.SurfAdmin" in response.text
    assert "toggleTheme" in response.text


def test_shared_admin_theme_contract():
    css = client.get("/static/admin/surf-admin.css")
    js = client.get("/static/admin/surf-admin.js")
    assert css.status_code == 200
    assert js.status_code == 200
    assert '[data-theme="dark"]' in css.text
    assert "setAttribute('data-theme', 'dark')" in js.text or 'setAttribute("data-theme", "dark")' in js.text


def test_landing_does_not_reference_admin_assets():
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/admin/surf-admin.css" not in response.text
    assert "/static/admin/surf-admin.js" not in response.text


def admin_cookie(monkeypatch):
    monkeypatch.setattr(admin, "verify_session", lambda token: True)
    monkeypatch.setattr(availability, "verify_session", lambda token: True)
    monkeypatch.setattr(photos, "verify_session", lambda token: True)
    monkeypatch.setattr(dashboard, "verify_session", lambda token: True)
    return {"asess": "test-session"}


@pytest.mark.parametrize("path", ["/admin/", "/availability/admin", "/photos/admin", "/dashboard/"])
def test_authenticated_admin_pages_reference_shared_assets(monkeypatch, path):
    response = client.get(path, cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    assert '<link rel="stylesheet" href="/static/admin/surf-admin.css">' in response.text
    assert '<script src="/static/admin/surf-admin.js"></script>' in response.text


@pytest.mark.parametrize("path", ["/admin/", "/availability/admin", "/photos/admin", "/dashboard/"])
def test_authenticated_admin_pages_share_nav_labels(monkeypatch, path):
    response = client.get(path, cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    for label in ["홈", "예약", "사진", "분석"]:
        assert f">{label}<" in response.text


def test_login_page_uses_surfirst_console_copy():
    response = client.get("/admin/login")
    assert response.status_code == 200
    assert "서퍼스트 운영 콘솔" in response.text
    assert "/static/admin/surf-admin.css" in response.text
