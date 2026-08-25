import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import admin, availability, dashboard, photos
from app.services import db


client = TestClient(app)


def test_shared_admin_css_served():
    response = client.get("/static/admin/surf-admin.css")
    assert response.status_code == 200
    assert "--sf-river" in response.text
    assert ".sf-app" in response.text
    assert ".sf-command-strip" in response.text
    assert ".sf-metric--attention" in response.text
    assert ".sf-metric--money" in response.text


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
    assert '<link rel="stylesheet" href="/static/admin/surf-admin.css?v=20260825-homemobile">' in response.text
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
    assert "/static/admin/surf-admin.css?v=20260825-homemobile" in response.text


def test_touch_targets_keep_40px_minimums():
    assert ".r-acts button { background:none; border:none; cursor:pointer; font-size:20px; padding:4px 3px; color:var(--sub); min-width:40px; min-height:40px; }" in availability.ADMIN_HTML
    assert ".r-acts button { font-size:21px; padding:4px 3px; min-width:40px; min-height:40px; }" in availability.ADMIN_HTML
    assert "min-width:40px; min-height:40px;" in admin.DASHBOARD_HTML
    assert ".memobtn { background:var(--field); border:1px solid var(--line); color:var(--sub);" in admin.DASHBOARD_HTML
    assert ".delrowbtn { background:transparent; border:none; color:var(--sub); font-size:16px;" in admin.DASHBOARD_HTML
    assert ".turn .tbtn { background:var(--field); border:1px solid var(--line); color:var(--sub);" in admin.DASHBOARD_HTML
    assert ".ibtn{background:var(--field);border:1px solid var(--line);color:var(--txt);" in dashboard.DASHBOARD_HTML
    assert "width:40px;height:40px;border-radius:10px;cursor:pointer;font-size:17px;" in dashboard.DASHBOARD_HTML
    assert ".rbtn{background:var(--field);border:1px solid var(--line);color:var(--sub);" in dashboard.DASHBOARD_HTML
    assert "border-radius:7px;font-size:12px;font-weight:700;padding:4px 9px;min-width:40px;min-height:40px;cursor:pointer;}" in dashboard.DASHBOARD_HTML
    assert ".report-tab { min-height: 40px;" in client.get("/static/admin/surf-admin.css").text
    assert "width:40px;height:40px;border-radius:10px;cursor:pointer;font-size:18px;" in dashboard.DASHBOARD_HTML
    assert ".delbtn { background:#ef4444; font-size:14px; padding:8px 14px; border-radius:8px; font-weight:700; flex-shrink:0; min-width:40px; min-height:40px; }" in photos.ADMIN_HTML
    assert ".thumb .xbtn { position:absolute; top:-6px; right:-6px; width:40px; height:40px; border-radius:50%;" in photos.ADMIN_HTML
    assert "cursor:pointer; padding:0; line-height:40px; text-align:center; }" in photos.ADMIN_HTML


def test_mobile_topbar_wraps_actions_below_brand():
    css = client.get("/static/admin/surf-admin.css").text
    assert ".sf-topbar { flex-wrap: wrap; align-items: flex-start; }" in css
    assert ".sf-topbar .sf-mobile-brand { width: 100%; }" in css


def test_sidebar_nav_is_protected_from_legacy_inline_nav_rules():
    css = client.get("/static/admin/surf-admin.css").text
    assert ".sf-sidebar .sf-nav { padding: 0; overflow: visible; }" in css
    assert ".sf-sidebar .sf-nav__link { background: transparent; border: 0; text-align: left; }" in css
    assert ".sf-sidebar .sf-nav__link[aria-current=\"page\"] { background: #ffffff; color: var(--sf-navy); }" in css


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
    assert "id=\"fresh-intents-note\"" in response.text
    assert "최근 7일" in response.text
    assert "sf-command-strip" in response.text
    assert "sf-metric--attention" in response.text
    assert "sf-metric--money" in response.text
    assert '<body class="sf-admin-home">' in response.text


def test_admin_home_filters_stale_booking_intents_from_visible_work_queue():
    assert "const INTENT_TTL_DAYS = 7;" in admin.DASHBOARD_HTML
    assert "function freshBookingIntents(rows){" in admin.DASHBOARD_HTML
    assert "const intents=freshBookingIntents(rawIntents);" in admin.DASHBOARD_HTML
    assert "document.getElementById('fresh-intents-note').textContent='최근 7일 문의만 표시';" in admin.DASHBOARD_HTML


def test_booking_intent_api_uses_recent_window_contract():
    assert admin.__dict__.get("BOOKING_INTENT_RECENT_DAYS") == 7
    assert "BOOKING_INTENT_RECENT_DAYS" in admin.api_intents.__code__.co_names
    assert "recent_days" in db.get_booking_intents.__code__.co_varnames


def test_admin_home_today_metric_targets_today_reservations_modal():
    assert """onclick="openCard('today-reservations')\"""" in admin.DASHBOARD_HTML
    assert "if(type==='today-reservations'){" in admin.DASHBOARD_HTML
    assert "오늘 예약" in admin.DASHBOARD_HTML


def test_admin_home_spacing_uses_consistent_mobile_grid_contract():
    css = client.get("/static/admin/surf-admin.css").text
    assert ".sf-admin-home .sf-page { padding: 20px; }" in css
    assert ".sf-admin-home .sf-page-head { margin-bottom: 12px; }" in css
    assert ".sf-admin-home .sf-command-strip { margin: 0 0 12px; padding: 12px; }" in css
    assert ".sf-admin-home .ops-metrics { gap: 10px; }" in css
    assert ".sf-admin-home .ops-layout { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 10px; align-items: start; }" in css
    assert ".sf-admin-home .ops-layout > .sf-panel { grid-column: span 2; }" in css
    assert ".sf-admin-home .ops-layout > section:nth-child(3), .sf-admin-home .ops-layout > section:nth-child(4) { min-height: 0; }" in css
    assert ".sf-admin-home .ops-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }" in css
    assert ".sf-admin-home .sf-metric { min-height: 92px; padding: 11px; }" in css
    assert ".sf-admin-home .ops-layout { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 8px; }" in css
    assert ".sf-admin-home .ops-layout > .sf-panel { grid-column: auto; }" in css
    assert ".sf-admin-home .sf-panel { padding: 11px; }" in css
    assert ".sf-admin-home .sf-section-title { margin-bottom: 8px; font-size: 13px; }" in css


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


def test_availability_admin_html_contains_focus_fallback_contract():
    assert "function focusAddForm(){" in availability.ADMIN_HTML
    assert "firstField.focus({preventScroll:true})" in availability.ADMIN_HTML
    assert "catch(_err){ firstField.focus(); }" in availability.ADMIN_HTML


def test_availability_admin_html_contains_summary_status_contract():
    for marker in [
        "여유",
        "주의",
        "마감",
        "seat-card",
        "sf-status--pending",
        "sf-status--full",
        "sf-status--ok",
    ]:
        assert marker in availability.ADMIN_HTML


def test_mobile_seat_board_is_compact_and_readable_without_horizontal_scroll():
    css = client.get("/static/admin/surf-admin.css").text
    assert ".seat-board { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; overflow: visible; padding-bottom: 0; }" in css
    assert ".seat-card { min-width: 0; min-height: 86px; padding: 7px 7px 6px; border-radius: 9px; }" in css
    assert ".seat-card__top { align-items: center; flex-direction: row; gap: 4px; font-size: 10px; }" in css
    assert ".seat-card__time { margin-top: 5px; font-size: 12px; font-weight: 900; }" in css
    assert ".seat-card__big { margin-top: 4px; font-size: 21px; }" in css
    assert ".seat-card__meta { margin-top: 4px; font-size: 10px; }" in css
    mobile_block = css.split("@media (max-width: 640px)", 1)[1].split("@media (max-width: 480px)", 1)[0]
    assert ".seat-board { display: flex; overflow-x: auto;" not in mobile_block


def test_availability_admin_html_contains_list_badges_and_actions_contract():
    for marker in [
        '<span class="sf-status sf-status--ok">예약</span>',
        '<span class="sf-status sf-status--pending">입금대기</span>',
        '<span class="sf-status sf-status--danger">노쇼</span>',
        '<span class="sf-status sf-status--muted">취소</span>',
        "const isCanceled = st==='취소' || st==='예약취소' || st==='취소됨';",
        "else badge = `<span class=\"sf-status sf-status--muted\">${esc(st)}</span>`;",
        ">확정</button>",
    ]:
        assert marker in availability.ADMIN_HTML


def test_availability_add_reservation_submits_and_resets_status():
    assert "fd.append('status', $('f_status').value);" in availability.ADMIN_HTML
    assert "$('f_status').value='예약';" in availability.ADMIN_HTML


def test_admin_home_uses_data_attribute_for_user_id_actions():
    assert "function attr(s){" in admin.DASHBOARD_HTML
    assert "function openUserFromElement(el){" in admin.DASHBOARD_HTML
    assert 'data-user-id="${attr(r.user_id)}"' in admin.DASHBOARD_HTML
    assert "openUser('${esc(r.user_id)}')" not in admin.DASHBOARD_HTML


def test_photos_page_has_delivery_regions(monkeypatch):
    response = client.get("/photos/admin", cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    for marker in [
        'id="photo-delivery"',
        'id="album-create-panel"',
        'id="list"',
        'role="status"',
        'aria-live="polite"',
        "앨범을 만들고 QR을 손님에게 보여주세요",
    ]:
        assert marker in response.text


def test_dashboard_page_has_report_regions(monkeypatch):
    response = client.get("/dashboard/", cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    for marker in [
        'id="analytics-report"',
        'id="p-ov"',
        'id="p-ch"',
        'id="p-cal"',
        "영업 리포트",
    ]:
        assert marker in response.text
