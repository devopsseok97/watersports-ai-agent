"""관리자 UI 자산 계약 테스트.

이전에는 codex가 생성한 오버라이드 CSS 문자열까지 정확히 비교했지만,
2026-08-26 재설계 이후 그 오버라이드는 없어졌다. 여기서는 재설계 후에도
반드시 지켜야 할 계약(공유 자산 참조, 네비 라벨, 규약 문자열, 홈 워크플로우 등)만 검증한다.
"""

import re
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import admin, availability, dashboard, photos
from app.services import db


client = TestClient(app)


# ---------- 공유 자산 ----------

def test_shared_admin_css_served():
    response = client.get("/static/admin/surf-admin.css")
    assert response.status_code == 200
    assert "--sf-river" in response.text
    assert ".sf-app" in response.text
    assert ".sf-metric" in response.text
    assert ".sf-status" in response.text
    assert ".sf-nav" in response.text


def test_shared_admin_js_served():
    response = client.get("/static/admin/surf-admin.js")
    assert response.status_code == 200
    assert "window.SurfAdmin" in response.text
    assert "toggleTheme" in response.text


def test_shared_admin_theme_contract():
    css = client.get("/static/admin/surf-admin.css").text
    js = client.get("/static/admin/surf-admin.js").text
    assert '[data-theme="dark"]' in css
    assert "setAttribute('data-theme', 'dark')" in js or 'setAttribute("data-theme", "dark")' in js


def test_landing_does_not_reference_admin_assets():
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/admin/surf-admin.css" not in response.text
    assert "/static/admin/surf-admin.js" not in response.text


# ---------- 공유 참조: 인증된 관리자 페이지 ----------

def admin_cookie(monkeypatch):
    monkeypatch.setattr(admin, "verify_session", lambda token: True)
    monkeypatch.setattr(availability, "verify_session", lambda token: True)
    monkeypatch.setattr(photos, "verify_session", lambda token: True)
    monkeypatch.setattr(dashboard, "verify_session", lambda token: True)
    return {"asess": "test-session"}


CSS_HREF_RE = re.compile(r'<link rel="stylesheet" href="/static/admin/surf-admin\.css\?v=[^"]+">')
JS_SRC_RE = re.compile(r'<script src="/static/admin/surf-admin\.js"></script>')


@pytest.mark.parametrize("path", ["/admin/", "/availability/admin", "/photos/admin", "/dashboard/"])
def test_authenticated_admin_pages_reference_shared_assets(monkeypatch, path):
    response = client.get(path, cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    assert CSS_HREF_RE.search(response.text), f"{path} 공유 CSS 링크 없음"
    assert JS_SRC_RE.search(response.text), f"{path} 공유 JS 참조 없음"


@pytest.mark.parametrize("path", ["/admin/", "/availability/admin", "/photos/admin", "/dashboard/"])
def test_authenticated_admin_pages_share_nav_labels(monkeypatch, path):
    response = client.get(path, cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    for label in ["홈", "예약", "사진", "분석"]:
        assert f">{label}<" in response.text, f"{path}에 {label} 라벨 없음"


# ---------- 로그인 ----------

def test_login_page_uses_surfirst_console_copy():
    response = client.get("/admin/login")
    assert response.status_code == 200
    assert "서퍼스트" in response.text and "운영 콘솔" in response.text
    assert CSS_HREF_RE.search(response.text)


# ---------- 터치 타겟 ----------

def test_shared_css_defines_touch_target_baseline():
    """모든 클릭 요소가 최소 40-44px 터치 영역을 갖도록 공용 토큰과 규칙이 있어야 한다."""
    css = client.get("/static/admin/surf-admin.css").text
    assert "--sf-tap: 44px" in css
    # 주요 인터랙션 요소가 최소 크기를 명시적으로 사용
    assert re.search(r"\.sf-btn\s*\{[^}]*min-height:\s*var\(--sf-tap\)", css)
    assert re.search(r"\.sf-icon-btn\s*\{[^}]*height:\s*40px", css)
    assert re.search(r"\.sf-nav__link\s*\{[^}]*min-height:", css)


# ---------- 모바일 네비 ----------

def test_mobile_uses_bottom_tab_nav():
    """모바일에서 sf-nav가 하단 고정 탭바로 동작해야 한다."""
    css = client.get("/static/admin/surf-admin.css").text
    assert re.search(r"\.sf-nav\s*\{[^}]*position:\s*fixed[^}]*bottom:\s*0", css)
    assert "grid-template-columns: repeat(4, 1fr)" in css


def test_desktop_uses_navy_sidebar():
    """900px 이상에서는 좌측 네이비 사이드바를 그리고 탭바를 해제한다."""
    css = client.get("/static/admin/surf-admin.css").text
    assert "@media (min-width: 900px)" in css
    assert "grid-template-columns: 208px minmax(0, 1fr)" in css


# ---------- 홈 ----------

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
        assert marker in response.text, f"홈 화면에 {marker} 영역 없음"
    assert "현장 상태" in response.text
    assert "예약 추가" in response.text
    assert "sf-metric--attention" in response.text
    assert "sf-metric--money" in response.text
    # 최근 7일 필터가 살아있는지
    assert "최근 7일" in response.text


def test_admin_home_filters_stale_booking_intents_from_visible_work_queue():
    assert "const INTENT_TTL_DAYS = 7;" in admin.DASHBOARD_HTML
    assert "function freshBookingIntents(rows)" in admin.DASHBOARD_HTML
    assert "const intents = freshBookingIntents(rawIntents);" in admin.DASHBOARD_HTML


def test_booking_intent_api_uses_recent_window_contract():
    assert admin.__dict__.get("BOOKING_INTENT_RECENT_DAYS") == 7
    assert "BOOKING_INTENT_RECENT_DAYS" in admin.api_intents.__code__.co_names
    assert "recent_days" in db.get_booking_intents.__code__.co_varnames


def test_admin_home_today_metric_targets_today_reservations_modal():
    assert """onclick="openCard('today-reservations')\"""" in admin.DASHBOARD_HTML
    assert "type === 'today-reservations'" in admin.DASHBOARD_HTML
    assert "오늘 예약" in admin.DASHBOARD_HTML


def test_admin_home_mobile_metric_order_prioritizes_field_work():
    html = admin.DASHBOARD_HTML
    ordered_labels = ["오늘 방문", "입금대기", "예약문의", "이번 달 수입"]
    positions = [html.index(f'<div class="sf-metric__label">{label}</div>') for label in ordered_labels]
    assert positions == sorted(positions), "홈 지표 순서: 오늘 방문 → 입금대기 → 예약문의 → 이번 달 수입"


def test_admin_home_timeline_uses_explicit_status_mapping():
    assert "function timelineStatusClass(status)" in admin.DASHBOARD_HTML
    assert "if(status==='예약') return 'sf-status--ok';" in admin.DASHBOARD_HTML
    assert "if(status==='입금대기') return 'sf-status--pending';" in admin.DASHBOARD_HTML
    assert "if(status==='노쇼') return 'sf-status--danger';" in admin.DASHBOARD_HTML
    assert "오늘 예약이 없습니다." in admin.DASHBOARD_HTML


def test_admin_home_uses_data_attribute_for_user_id_actions():
    """user_id는 onclick 인라인이 아니라 data 속성으로 전달해야 XSS 안전하다."""
    assert "function attr(s)" in admin.DASHBOARD_HTML
    assert "function openUserFromElement(el)" in admin.DASHBOARD_HTML
    assert 'data-user-id="${attr(r.user_id)}"' in admin.DASHBOARD_HTML
    assert "openUser('${esc(r.user_id)}')" not in admin.DASHBOARD_HTML


# ---------- 예약 ----------

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


# ---------- 사진 ----------

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


# ---------- 분석 ----------

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
