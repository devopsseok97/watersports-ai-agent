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


def test_touch_targets_keep_40px_minimums():
    assert ".r-acts button { background:none; border:none; cursor:pointer; font-size:20px; padding:4px 3px; color:var(--sub); min-width:40px; min-height:40px; }" in availability.ADMIN_HTML
    assert ".r-acts button { font-size:21px; padding:4px 3px; min-width:40px; min-height:40px; }" in availability.ADMIN_HTML
    assert ".ibtn{background:var(--field);border:1px solid var(--line);color:var(--txt);" in dashboard.DASHBOARD_HTML
    assert "width:40px;height:40px;border-radius:10px;cursor:pointer;font-size:17px;" in dashboard.DASHBOARD_HTML
    assert ".rbtn{background:var(--field);border:1px solid var(--line);color:var(--sub);" in dashboard.DASHBOARD_HTML
    assert "border-radius:7px;font-size:12px;font-weight:700;padding:4px 9px;min-width:40px;min-height:40px;cursor:pointer;}" in dashboard.DASHBOARD_HTML
    assert ".tab{background:none;border:none;border-bottom:3px solid transparent;" in dashboard.DASHBOARD_HTML
    assert "color:var(--sub);font-size:14px;font-weight:700;padding:10px 14px; min-width:40px; min-height:40px;" in dashboard.DASHBOARD_HTML
    assert "width:40px;height:40px;border-radius:10px;cursor:pointer;font-size:18px;" in dashboard.DASHBOARD_HTML
    assert ".delbtn { background:#ef4444; font-size:14px; padding:8px 14px; border-radius:8px; font-weight:700; flex-shrink:0; min-width:40px; min-height:40px; }" in photos.ADMIN_HTML
    assert ".thumb .xbtn { position:absolute; top:-6px; right:-6px; width:40px; height:40px; border-radius:50%;" in photos.ADMIN_HTML
    assert "cursor:pointer; padding:0; line-height:40px; text-align:center; }" in photos.ADMIN_HTML


def test_admin_home_has_operations_console_regions(monkeypatch):
    response = client.get("/admin/", cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    for marker in [
        'id="ops-alerts"',
        'id="today-timeline"',
        'id="intents"',
        'id="convos"',
        'href="/availability/admin"',
    ]:
        assert marker in response.text
    assert "오늘 운영" in response.text
    assert "예약 추가" in response.text


def test_admin_home_today_metric_targets_today_reservations_modal():
    assert """onclick="openCard('today-reservations')\"""" in admin.DASHBOARD_HTML
    assert "if(type==='today-reservations'){" in admin.DASHBOARD_HTML
    assert "오늘 예약" in admin.DASHBOARD_HTML


def test_admin_home_timeline_uses_explicit_status_mapping():
    assert "function timelineStatusClass(status){" in admin.DASHBOARD_HTML
    assert "if(status==='예약') return 'sf-status--ok';" in admin.DASHBOARD_HTML
    assert "if(status==='입금대기') return 'sf-status--pending';" in admin.DASHBOARD_HTML
    assert "if(status==='노쇼') return 'sf-status--danger';" in admin.DASHBOARD_HTML
    assert "if(status==='취소'||status==='예약취소'||status==='취소됨') return 'sf-status--muted';" in admin.DASHBOARD_HTML
    assert "return 'sf-status--muted';" in admin.DASHBOARD_HTML
    assert "오늘 예약이 없습니다." in admin.DASHBOARD_HTML


def test_availability_page_has_workbench_regions(monkeypatch):
    response = client.get("/availability/admin", cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    for marker in [
        'id="reservation-workbench"',
        'id="quick-add-panel"',
        'id="summary"',
        'id="list"',
        "잔여석",
        "예약 타임라인",
        "입금대기",
    ]:
        assert marker in response.text
