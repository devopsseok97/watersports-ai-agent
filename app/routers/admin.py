"""사장님용 웹 관리자 대시보드."""
import secrets
import logging
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import settings
from app.services.auth import verify_session, make_token, SESSION_COOKIE
from app.services.ratelimit import (
    client_key,
    login_locked,
    record_login_failure,
    record_login_success,
)
from app.services.db import (
    get_recent_conversations,
    get_booking_intents,
    get_user_conversations,
    update_conversation,
    set_conversation_memo,
    delete_conversation,
    get_stats,
)
from app.services import availability as av

logger = logging.getLogger(__name__)
router = APIRouter()
BOOKING_INTENT_RECENT_DAYS = 7


def require_admin(asess: str | None = Cookie(default=None)):
    if not verify_session(asess):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다.")


@router.get("/login", response_class=HTMLResponse)
async def login_page(asess: str | None = Cookie(default=None)):
    if verify_session(asess):
        return RedirectResponse(url="/admin/", status_code=302)
    return HTMLResponse(LOGIN_HTML.replace("{ERROR}", ""))


@router.post("/login")
async def login_submit(
    request: Request,
    password: str = Form(...),
    remember: str = Form(default=""),
):
    key = client_key(request)
    if login_locked("admin", key):
        return HTMLResponse(
            LOGIN_HTML.replace("{ERROR}", '<div class="error">시도가 너무 많습니다. 10분 후 다시 시도해 주세요.</div>'),
            status_code=429,
        )

    expected = getattr(settings, "admin_password", "") or ""
    ok = bool(expected) and secrets.compare_digest(password, expected)
    if not ok:
        record_login_failure("admin", key)
        return HTMLResponse(
            LOGIN_HTML.replace("{ERROR}", '<div class="error">비밀번호가 올바르지 않습니다.</div>'),
            status_code=401,
        )
    record_login_success("admin", key)
    token = make_token(expected)
    response = RedirectResponse(url="/admin/", status_code=302)
    max_age = 30 * 24 * 3600 if remember == "1" else None
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, samesite="lax")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/api/stats")
async def api_stats(_=Depends(require_admin)):
    try:
        return await get_stats()
    except Exception as e:
        logger.error(f"stats 조회 실패: {e}")
        return {"total_conversations": 0, "booking_intents": 0, "today_conversations": 0}


@router.get("/api/intents")
async def api_intents(_=Depends(require_admin)):
    try:
        return await get_booking_intents(limit=100, recent_days=BOOKING_INTENT_RECENT_DAYS)
    except Exception as e:
        logger.error(f"intents 조회 실패: {e}")
        return []


@router.get("/api/conversations")
async def api_conversations(_=Depends(require_admin)):
    try:
        return await get_recent_conversations(limit=100)
    except Exception as e:
        logger.error(f"conversations 조회 실패: {e}")
        return []


@router.get("/api/user")
async def api_user(user_id: str, _=Depends(require_admin)):
    try:
        return await get_user_conversations(user_id, limit=100)
    except Exception as e:
        logger.error(f"user 대화 조회 실패: {e}")
        return []


@router.post("/api/conversation/update")
async def api_conv_update(
    id: int = Form(...),
    user_message: str = Form(""),
    bot_reply: str = Form(""),
    _=Depends(require_admin),
):
    try:
        row = await update_conversation(id, user_message, bot_reply)
        return {"ok": True, "conversation": row}
    except Exception as e:
        logger.error(f"대화 수정 실패: {e}")
        return {"ok": False}


@router.post("/api/conversation/memo")
async def api_conv_memo(
    id: int = Form(...),
    memo: str = Form(""),
    _=Depends(require_admin),
):
    try:
        row = await set_conversation_memo(id, memo)
        return {"ok": True, "conversation": row}
    except Exception as e:
        logger.error(f"대화 메모 저장 실패: {e}")
        return {"ok": False}


@router.post("/api/conversation/delete")
async def api_conv_delete(id: int = Form(...), _=Depends(require_admin)):
    try:
        await delete_conversation(id)
        return {"ok": True}
    except Exception as e:
        logger.error(f"대화 삭제 실패: {e}")
        return {"ok": False}


@router.get("/api/reservation-stats")
async def api_reservation_stats(_=Depends(require_admin)):
    try:
        return await av.get_reservation_stats()
    except Exception as e:
        logger.error(f"예약 통계 조회 실패: {e}")
        return {
            "total_reservations": 0, "total_people": 0, "total_revenue": 0,
            "today_reservations": 0, "today_people": 0, "today_revenue": 0,
            "month_reservations": 0, "month_people": 0, "month_revenue": 0, "month": "",
            "noshow_total": 0, "noshow_rate": 0, "month_noshow": 0,
            "month_noshow_rate": 0, "total_all": 0,
            "pending_total": 0, "pending_people": 0, "pending_amount": 0,
        }


@router.get("/api/reservations")
async def api_reservations(_=Depends(require_admin)):
    try:
        return await av.get_recent_reservations(limit=200)
    except Exception as e:
        logger.error(f"예약 목록 조회 실패: {e}")
        return []


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard(asess: str | None = Cookie(default=None)):
    if not verify_session(asess):
        return RedirectResponse(url="/admin/login", status_code=302)
    return HTMLResponse(DASHBOARD_HTML)


LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#09090d">
<title>서퍼스트 관리자 로그인</title>
<link rel="stylesheet" href="/static/admin/surf-admin.css">
</head>
<body class="sf-login">
<main class="sf-login-card">
  <div class="sf-login-brand">
    <div class="sf-brand" aria-label="서퍼스트 운영 콘솔">서퍼스트<small>운영 콘솔</small></div>
  </div>
  {ERROR}
  <form method="post" action="/admin/login" class="sf-login-form">
    <div class="sf-field">
      <label>비밀번호</label>
      <input type="password" name="password" placeholder="비밀번호를 입력하세요" autofocus autocomplete="current-password">
    </div>
    <label class="sf-check"><input type="checkbox" name="remember" value="1"> 자동 로그인 30일 유지</label>
    <button type="submit" class="sf-btn sf-btn--primary">로그인</button>
  </form>
</main>
</body>
</html>"""


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#09090d" media="(prefers-color-scheme: dark)">
<link rel="manifest" href="/static/manifest.json">
<link rel="apple-touch-icon" href="/static/icon-192.png">
<link rel="stylesheet" href="/static/admin/surf-admin.css">
<title>서퍼스트 관리자 · 홈</title>
<style>
  :root {
    --bg:#f6f8fa; --card:#ffffff; --line:#d0d7de; --txt:#1f2328; --sub:#57606a;
    --accent:#6366f1; --accent-soft:#eef2ff;
    --green:#1a7f4f; --green-soft:#dafbe1;
    --warn:#9a6700; --warn-soft:#fff8c5;
    --full:#d1242f; --full-bg:#ffebe9;
    --field:#f6f8fa; --shadow:0 1px 3px rgba(0,0,0,.08);
    --header-bg:rgba(255,255,255,.92);
  }
  [data-theme="dark"] {
    --bg:#09090d; --card:#111116; --line:#1e2028; --txt:#e4e7ef; --sub:#6b7280;
    --accent:#818cf8; --accent-soft:#1a1b35;
    --green:#34d399; --green-soft:#06190e;
    --warn:#fbbf24; --warn-soft:#1c1500;
    --full:#f87171; --full-bg:#1a0606;
    --field:#0d0f14; --shadow:none;
    --header-bg:rgba(9,9,13,.85);
  }
  * { box-sizing:border-box; }
  html { -webkit-text-size-adjust:100%; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
         background:var(--bg); color:var(--txt); font-size:17px; line-height:1.45; }

  /* ===== 헤더 / 네비 ===== */
  header { background:var(--header-bg); backdrop-filter:saturate(180%) blur(12px);
           -webkit-backdrop-filter:saturate(180%) blur(12px);
           border-bottom:1px solid var(--line); position:sticky; top:0; z-index:10; }
  .htop { padding:14px 18px; display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .brand { font-size:19px; font-weight:800; white-space:nowrap; }
  .brand span { color:var(--sub); font-weight:600; font-size:14px; margin-left:4px; }
  .htools { display:flex; align-items:center; gap:6px; }
  .themebtn { background:var(--field); border:1px solid var(--line); color:var(--txt);
              width:40px; height:40px; border-radius:10px; cursor:pointer; font-size:19px;
              padding:0; display:flex; align-items:center; justify-content:center; }
  .refresh { background:var(--field); border:1px solid var(--line); color:var(--txt);
             height:40px; border-radius:10px; cursor:pointer; font-size:14px;
             font-weight:700; padding:0 13px; white-space:nowrap; }
  .refresh:active { background:var(--accent); color:#fff; border-color:var(--accent); }
  .logoutbtn { color:var(--sub); font-size:13px; font-weight:600; text-decoration:none;
               padding:9px 12px; border-radius:10px; background:var(--field);
               border:1px solid var(--line); white-space:nowrap; }
  .logoutbtn:hover { color:var(--txt); }
  nav { display:flex; gap:6px; padding:0 12px 12px; overflow-x:auto; }
  nav a { flex:1; text-align:center; white-space:nowrap; text-decoration:none; color:var(--sub);
          font-size:15px; font-weight:700; padding:10px 10px; border-radius:10px;
          background:var(--field); border:1px solid var(--line); }
  nav a.active { color:#fff; background:var(--accent); border-color:var(--accent); }

  main { padding:18px; max-width:1000px; margin:0 auto; }

  /* ===== 통계 카드 ===== */
  .cards { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; margin-bottom:24px; }
  .stat { background:var(--card); border:1px solid var(--line); border-radius:16px;
          padding:18px; box-shadow:var(--shadow); }
  .stat .label { color:var(--sub); font-size:14px; margin-bottom:10px; font-weight:600; }
  .stat .value { font-size:34px; font-weight:900; line-height:1; }
  .stat .value.money { font-size:26px; }
  .stat .sublabel { color:var(--sub); font-size:12px; margin-top:10px; font-weight:600; opacity:.8; }
  .stat.accent .value { color:var(--accent); }
  .stat.green { background:var(--green-soft); border-color:var(--green); }
  .stat.green .value { color:var(--green); }
  .stat.warn { background:var(--warn-soft); border-color:var(--warn); }
  .stat.warn .value { color:var(--warn); }
  .stat.danger { background:var(--full-bg); border-color:var(--full); }
  .stat.danger .value { color:var(--full); }
  .stat.amber { background:rgba(245,158,11,.1); border-color:#f59e0b; }
  .stat.amber .value { color:#d97706; }
  [data-theme="dark"] .stat.amber { background:rgba(251,191,36,.07); border-color:rgba(251,191,36,.35); }
  [data-theme="dark"] .stat.amber .value { color:#fbbf24; }
  .stat.clickable { cursor:pointer; transition:transform .1s, border-color .12s; }
  .stat.clickable:hover { border-color:var(--accent); }
  .stat.clickable:active { transform:scale(.98); }
  @media (min-width:760px){ .cards { grid-template-columns:repeat(6,1fr); } }

  /* ===== 모바일 ===== */
  @media (max-width:560px){
    main { padding-bottom:max(20px, env(safe-area-inset-bottom)); }
    .kpirow { grid-template-columns:repeat(2,1fr); }
    .kpirow .kpi:last-child { grid-column:1 / -1; }
    .revbox { grid-template-columns:repeat(2,1fr); }
    .revbox .b:last-child { grid-column:1 / -1; }
  }

  /* ===== 수입 분석 ===== */
  .kpirow { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:16px; }
  .kpi { background:var(--card); border:1px solid var(--line); border-radius:12px;
         padding:14px; text-align:center; box-shadow:var(--shadow); }
  .kpi .k { color:var(--sub); font-size:13px; font-weight:600; margin-bottom:6px; }
  .kpi .v { font-size:18px; font-weight:900; line-height:1.2; }
  .kpi .v.up { color:var(--green); }
  .kpi .v.dn { color:var(--full); }
  .chartrow { display:grid; grid-template-columns:1fr; gap:16px; margin-bottom:28px; }
  .chartbox { background:var(--card); border:1px solid var(--line); border-radius:16px;
              padding:20px; box-shadow:var(--shadow); }
  .chartbox .clabel { color:var(--sub); font-size:14px; font-weight:700; margin-bottom:16px; }
  @media (min-width:700px){ .chartrow { grid-template-columns:3fr 2fr; } }

  /* ===== 수입 요약 박스 ===== */
  .revbox { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:16px; }
  .revbox .b { background:var(--field); border:1px solid var(--line); border-radius:12px;
               padding:14px; text-align:center; }
  .revbox .b .k { color:var(--sub); font-size:13px; font-weight:600; margin-bottom:6px; }
  .revbox .b .v { font-size:20px; font-weight:900; }
  .revbox .b.hi { background:var(--warn-soft); border-color:var(--warn); }
  .revbox .b.hi .v { color:var(--warn); }
  .resrow { display:flex; align-items:center; gap:12px; padding:13px 14px; border:1px solid var(--line);
            border-radius:12px; margin-bottom:8px; background:var(--card); }
  .resrow .d { text-align:center; min-width:54px; }
  .resrow .d .dd { font-weight:800; font-size:14px; }
  .resrow .d .tt { color:var(--accent); font-size:13px; font-weight:700; }
  .resrow .c { flex:1; min-width:0; }
  .resrow .c .nm { font-weight:700; font-size:16px; }
  .resrow .c .mt { color:var(--sub); font-size:13px; margin-top:2px; }
  .resrow .r { text-align:right; white-space:nowrap; }
  .resrow .r .pp { font-weight:800; font-size:15px; }
  .resrow .r .am { color:var(--green); font-weight:800; font-size:14px; margin-top:2px; }

  h2 { font-size:18px; margin:26px 0 14px; font-weight:800; }

  /* ===== 카드 리스트 ===== */
  .item { background:var(--card); border:1px solid var(--line); border-radius:14px;
          padding:16px; margin-bottom:10px; box-shadow:var(--shadow); }
  .item .head { display:flex; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap; }
  .item .time { color:var(--sub); font-size:14px; }
  .item .uid { color:var(--sub); font-family:monospace; font-size:13px; }
  .tag { display:inline-block; background:var(--warn); color:#fff; font-size:13px;
         font-weight:700; padding:3px 9px; border-radius:7px; }
  .item .q { font-size:17px; font-weight:600; }
  .item .a { color:var(--sub); font-size:16px; margin-top:6px; }
  .item.clickable { cursor:pointer; transition:border-color .12s; }
  .item.clickable:hover { border-color:var(--accent); }
  .item .arrow { color:var(--sub); font-size:18px; }
  .item .head .spacer { margin-left:auto; }
  .memobtn { background:var(--field); border:1px solid var(--line); color:var(--sub);
             border-radius:8px; font-size:14px; font-weight:700; cursor:pointer; padding:5px 10px;
             min-width:40px; min-height:40px; }
  .memobtn:active { color:var(--accent); }
  .delrowbtn { background:transparent; border:none; color:var(--sub); font-size:16px;
               cursor:pointer; padding:4px 8px; border-radius:6px; transition:color .12s, background .12s;
               min-width:40px; min-height:40px; }
  .delrowbtn:hover { color:#ef4444; background:rgba(239,68,68,.1); }
  .memo-view { margin-top:10px; padding:10px 12px; background:var(--warn-soft);
               border:1px solid var(--warn); border-radius:10px; font-size:15px;
               color:var(--txt); white-space:pre-wrap; word-break:break-word; }
  .memo-view b { color:var(--warn); }
  .memo-edit { margin-top:10px; }
  .memo-edit textarea { width:100%; background:var(--field); border:1px solid var(--line);
              color:var(--txt); border-radius:10px; padding:10px 12px; font-size:15px;
              font-family:inherit; line-height:1.5; resize:vertical; }
  .memo-edit .bar { display:flex; gap:8px; margin-top:8px; }
  .memo-edit .bar button { flex:1; border:none; border-radius:10px; padding:11px;
                           font-size:15px; font-weight:700; cursor:pointer; }
  .memo-edit .bar .ok { background:var(--accent); color:#fff; }
  .memo-edit .bar .cancel { background:var(--field); border:1px solid var(--line); color:var(--txt); }
  .empty { color:var(--sub); padding:28px; text-align:center; font-size:16px;
           background:var(--card); border:1px dashed var(--line); border-radius:14px; }

  /* ===== 고객 상세 모달 ===== */
  .modal-bg { position:fixed; inset:0; background:rgba(0,0,0,.55); display:none;
              align-items:flex-end; justify-content:center; z-index:100; }
  .modal-bg.show { display:flex; }
  .modal { background:var(--card); width:100%; max-width:640px; max-height:88vh;
           border-radius:18px 18px 0 0; display:flex; flex-direction:column; overflow:hidden; }
  .modal-head { padding:18px 20px; border-bottom:1px solid var(--line);
                display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .modal-head .t { font-size:18px; font-weight:800; }
  .modal-head .u { color:var(--sub); font-size:13px; font-family:monospace; margin-top:3px; }
  .modal-head .x { background:var(--field); border:1px solid var(--line); color:var(--txt);
                   width:40px; height:40px; border-radius:10px; font-size:20px; cursor:pointer; }
  .modal-body { padding:16px 20px; overflow-y:auto; }
  .turn { margin-bottom:18px; }
  .turn .ts { color:var(--sub); font-size:13px; margin-bottom:6px; }
  .bubble { padding:11px 14px; border-radius:14px; font-size:16px; line-height:1.5;
            white-space:pre-wrap; word-break:break-word; }
  .bubble.user { background:var(--accent-soft); color:var(--txt); border-radius:14px 14px 14px 4px; }
  .bubble.bot { background:var(--field); border:1px solid var(--line); margin-top:6px;
                border-radius:14px 14px 4px 14px; }
  .turn .who { font-size:13px; font-weight:700; color:var(--sub); margin-bottom:4px; }
  .turn .booking { display:inline-block; background:var(--warn); color:#fff; font-size:12px;
                   font-weight:700; padding:2px 8px; border-radius:6px; margin-left:6px; }
  .turn .tools { display:flex; gap:4px; margin-left:auto; }
  .turn .ts { display:flex; align-items:center; }
  .turn .tbtn { background:var(--field); border:1px solid var(--line); color:var(--sub);
                border-radius:8px; font-size:15px; cursor:pointer; padding:4px 8px;
                min-width:40px; min-height:40px; }
  .turn .tbtn:active { color:var(--accent); }
  .turn textarea { width:100%; background:var(--field); border:1px solid var(--line);
                   color:var(--txt); border-radius:10px; padding:10px 12px; font-size:15px;
                   font-family:inherit; line-height:1.5; resize:vertical; }
  .turn .editrow { margin-top:8px; }
  .turn .editrow label { font-size:13px; font-weight:700; color:var(--sub);
                         display:block; margin-bottom:4px; }
  .turn .savebar { display:flex; gap:8px; margin-top:10px; }
  .turn .savebar button { flex:1; border:none; border-radius:10px; padding:11px;
                          font-size:15px; font-weight:700; cursor:pointer; }
  .turn .savebar .ok { background:var(--accent); color:#fff; }
  .turn .savebar .cancel { background:var(--field); border:1px solid var(--line); color:var(--txt); }
  @media (min-width:560px){ .modal-bg { align-items:center; } .modal { border-radius:18px; } }
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="/static/admin/surf-admin.js"></script>
</head>
<body>
<div class="sf-app">
  <aside class="sf-sidebar">
    <div class="sf-brand">서퍼스트<small>운영 콘솔</small></div>
    <nav class="sf-nav" aria-label="관리자 메뉴">
      <a class="sf-nav__link" href="/admin/" aria-current="page">홈</a>
      <a class="sf-nav__link" href="/availability/admin">예약</a>
      <a class="sf-nav__link" href="/photos/admin">사진</a>
      <a class="sf-nav__link" href="/dashboard/">분석</a>
    </nav>
  </aside>
  <div class="sf-main">
    <header class="sf-topbar">
      <div class="sf-mobile-brand">서퍼스트 운영 콘솔</div>
      <div class="sf-actions">
        <button class="sf-btn sf-btn--ghost" id="themebtn" type="button">어둡게</button>
        <button class="sf-btn sf-btn--ghost" onclick="loadAll()" type="button">새로고침</button>
        <a class="sf-btn sf-btn--ghost" href="/admin/logout">로그아웃</a>
      </div>
    </header>
    <main class="sf-page">
      <div class="sf-page-head">
        <div>
          <div class="sf-eyebrow">오늘 운영</div>
          <h1 class="sf-page-title">서퍼스트 현장 상태</h1>
          <p class="sf-page-sub" id="today-label">오늘 예약과 문의를 확인하세요.</p>
        </div>
        <div class="sf-actions">
          <a class="sf-btn sf-btn--primary" href="/availability/admin">예약 추가</a>
          <button class="sf-btn sf-btn--ghost" onclick="loadAll()" type="button">새로고침</button>
        </div>
      </div>

      <div class="sf-command-strip" aria-label="운영 요약">
        <div><b>오늘 현장 우선순위</b><span>입금대기, 오늘 방문, 최근 예약문의를 먼저 처리하세요.</span></div>
        <div class="sf-command-strip__meta" id="fresh-intents-note">최근 7일 문의만 표시</div>
      </div>

      <div class="sf-card-grid ops-metrics">
        <button class="sf-metric sf-metric--clickable sf-metric--hero" type="button" onclick="openCard('today-reservations')">
          <div class="sf-metric__label">오늘 방문</div>
          <div class="sf-metric__value" id="s-today-ppl">-</div>
          <div class="sf-metric__note" id="s-today-rev">-</div>
        </button>
        <button class="sf-metric sf-metric--clickable sf-metric--money" type="button" onclick="openCard('revenue')">
          <div class="sf-metric__label">이번 달 수입</div>
          <div class="sf-metric__value money" id="s-revenue">-</div>
          <div class="sf-metric__note" id="s-month-ppl">-</div>
        </button>
        <button class="sf-metric sf-metric--clickable sf-metric--attention" type="button" onclick="openCard('pending')">
          <div class="sf-metric__label">입금대기</div>
          <div class="sf-metric__value" id="s-pending">-</div>
          <div class="sf-metric__note" id="s-pending-sub">-</div>
        </button>
        <button class="sf-metric sf-metric--clickable sf-metric--signal" type="button" onclick="openCard('intents')">
          <div class="sf-metric__label">예약문의</div>
          <div class="sf-metric__value" id="s-intents">-</div>
          <div class="sf-metric__note">최근 7일 의향 고객</div>
        </button>
      </div>

      <div class="ops-layout">
        <section class="sf-panel">
          <h2 class="sf-section-title">처리할 일</h2>
          <div id="ops-alerts" class="ops-alerts"><div class="sf-empty">불러오는 중...</div></div>
        </section>
        <section class="sf-panel">
          <h2 class="sf-section-title">오늘 예약 타임라인</h2>
          <div id="today-timeline" class="timeline-list"><div class="sf-empty">불러오는 중...</div></div>
        </section>
        <section class="sf-panel">
          <h2 class="sf-section-title">예약 의향 고객</h2>
          <div id="intents"><div class="sf-empty">불러오는 중...</div></div>
        </section>
        <section class="sf-panel">
          <h2 class="sf-section-title">최근 대화</h2>
          <div id="convos"><div class="sf-empty">불러오는 중...</div></div>
        </section>
      </div>
    </main>
  </div>
</div>

<div class="modal-bg" id="modal" onclick="if(event.target===this)closeUser()">
  <div class="modal">
    <div class="modal-head">
      <div>
        <div class="t">고객 대화 상세</div>
        <div class="u" id="m-uid"></div>
      </div>
      <button class="x" onclick="closeUser()">✕</button>
    </div>
    <div class="modal-body" id="m-body"></div>
  </div>
</div>

<div class="modal-bg" id="cardmodal" onclick="if(event.target===this)closeCard()">
  <div class="modal">
    <div class="modal-head">
      <div><div class="t" id="cm-title">상세</div></div>
      <button class="x" onclick="closeCard()">✕</button>
    </div>
    <div class="modal-body" id="cm-body"></div>
  </div>
</div>

<script>
/* ===== 차트 ===== */
let _mChart=null, _pChart=null;
const INTENT_TTL_DAYS = 7;

function buildCharts(list){
  const monthCanvas=document.getElementById('monthChart');
  const progCanvas=document.getElementById('progChart');
  if(!monthCanvas || !progCanvas || typeof Chart==='undefined') return;
  const ok=(list||[]).filter(r=>(r.status||'예약')==='예약');
  const now=new Date();
  const months=[];
  for(let i=5;i>=0;i--){
    const d=new Date(now.getFullYear(),now.getMonth()-i,1);
    months.push(d.toISOString().slice(0,7));
  }
  const mMap={};
  ok.forEach(r=>{ const m=(r.slot_date||'').slice(0,7); if(m) mMap[m]=(mMap[m]||0)+(Number(r.amount)||0); });

  const thisM=months[5], lastM=months[4];
  const thisAmt=mMap[thisM]||0, lastAmt=mMap[lastM]||0;
  const diffPct=lastAmt>0?Math.round((thisAmt-lastAmt)/lastAmt*100):null;
  const totalPpl=ok.reduce((s,r)=>s+(Number(r.people)||0),0);
  const totalAmt=ok.reduce((s,r)=>s+(Number(r.amount)||0),0);
  const avgPer=totalPpl>0?Math.round(totalAmt/totalPpl):0;

  document.getElementById('kpi-month').textContent=won(thisAmt);
  const diffEl=document.getElementById('kpi-diff');
  if(diffPct===null){ diffEl.textContent='-'; diffEl.className='v'; }
  else{ diffEl.textContent=(diffPct>=0?'▲ ':'▼ ')+Math.abs(diffPct)+'%'; diffEl.className='v '+(diffPct>0?'up':diffPct<0?'dn':''); }
  document.getElementById('kpi-avg').textContent=avgPer>0?won(avgPer):'-';

  const byProg={};
  ok.forEach(r=>{ const p=r.program||'기타'; byProg[p]=(byProg[p]||0)+(Number(r.amount)||0); });
  const pLabels=Object.keys(byProg), pData=Object.values(byProg);

  const isDark=document.documentElement.getAttribute('data-theme')==='dark';
  const gridC=isDark?'rgba(255,255,255,.05)':'rgba(0,0,0,.05)';
  const txtC=isDark?'#6b7280':'#57606a';
  const barMain=isDark?'#818cf8':'#6366f1';
  const barDim=isDark?'rgba(129,140,248,.2)':'rgba(99,102,241,.15)';
  const barHover=isDark?'#a5b4fc':'#818cf8';
  const borderC=isDark?'#111116':'#ffffff';
  const COLORS=isDark
    ?['#818cf8','#34d399','#fbbf24','#f87171','#60a5fa','#a78bfa','#fb923c','#94a3b8']
    :['#6366f1','#10b981','#f59e0b','#ef4444','#3b82f6','#8b5cf6','#f97316','#64748b'];

  if(_mChart) _mChart.destroy();
  _mChart=new Chart(monthCanvas,{
    type:'bar',
    data:{
      labels:months.map(m=>m.slice(5)+'월'),
      datasets:[{
        data:months.map(m=>+(((mMap[m]||0)/10000).toFixed(1))),
        backgroundColor:months.map((_,i)=>i===5?barMain:barDim),
        hoverBackgroundColor:months.map((_,i)=>i===5?barHover:barDim.replace('.2)','.35)').replace('.15)','.3)')),
        borderRadius:8, borderSkipped:false,
      }]
    },
    options:{
      plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>ctx.raw+'만원'}}},
      scales:{
        y:{ticks:{color:txtC,callback:v=>v+'만'},grid:{color:gridC},beginAtZero:true,border:{display:false}},
        x:{ticks:{color:txtC},grid:{display:false},border:{display:false}}
      }
    }
  });

  if(_pChart) _pChart.destroy();
  _pChart=pLabels.length?new Chart(progCanvas,{
    type:'doughnut',
    data:{
      labels:pLabels,
      datasets:[{data:pData, backgroundColor:COLORS, borderWidth:3, borderColor:borderC, hoverOffset:8}]
    },
    options:{
      plugins:{
        legend:{position:'bottom',labels:{color:txtC,font:{size:12},padding:12,boxWidth:10,boxHeight:10,
               borderRadius:4,useBorderRadius:true}},
        tooltip:{callbacks:{label:ctx=>ctx.label+' · '+won(ctx.raw)}}
      },
      cutout:'65%'
    }
  }):null;
}

function fmt(ts){ if(!ts)return'-'; const d=new Date(ts); return d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function attr(s){ return esc(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function uid(s){ return s?esc(String(s).slice(0,8))+'…':'-'; }
function won(n){ return (Number(n)||0).toLocaleString('ko-KR')+'원'; }
function todayKey(){
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const out={};
  parts.forEach(p=>{ if(p.type!=='literal') out[p.type]=p.value; });
  return (out.year||'')+'-'+(out.month||'')+'-'+(out.day||'');
}
function timelineStatusClass(status){
  if(status==='예약') return 'sf-status--ok';
  if(status==='입금대기') return 'sf-status--pending';
  if(status==='노쇼') return 'sf-status--danger';
  if(status==='취소'||status==='예약취소'||status==='취소됨') return 'sf-status--muted';
  return 'sf-status--muted';
}
function todayReservations(list){
  const today=todayKey();
  return (list||[]).filter(r=>r.slot_date===today).sort((a,b)=>String(a.time_slot||'').localeCompare(String(b.time_slot||'')));
}
function freshBookingIntents(rows){
  const cutoff = Date.now() - INTENT_TTL_DAYS * 24 * 60 * 60 * 1000;
  return (rows||[]).filter(r=>{
    if(!r.created_at) return true;
    const ts = Date.parse(r.created_at);
    return Number.isNaN(ts) || ts >= cutoff;
  });
}

async function loadAll(){
  try {
    const [stats,rawIntents,rawConvos,resStats,rawResList]=await Promise.all([
      fetch('api/stats').then(r=>r.json()),
      fetch('api/intents').then(r=>r.json()),
      fetch('api/conversations').then(r=>r.json()),
      fetch('api/reservation-stats').then(r=>r.json()),
      fetch('api/reservations').then(r=>r.json()),
    ]);
    const intents=freshBookingIntents(rawIntents);
    const convos=Array.isArray(rawConvos)?rawConvos:[];
    const resList=Array.isArray(rawResList)?rawResList:[];
    window._convosAll=convos||[];
    window._intentsAll=intents||[];
    window._resStats=resStats||{};
    window._resList=resList||[];

    buildCharts(window._resList);

    document.getElementById('today-label').textContent=SurfAdmin.todayLabel()+' 기준';
    document.getElementById('fresh-intents-note').textContent='최근 7일 문의만 표시';
    document.getElementById('s-today-ppl').textContent=(resStats.today_people??0)+'명';
    document.getElementById('s-today-rev').textContent=SurfAdmin.won(resStats.today_revenue);
    document.getElementById('s-revenue').textContent=SurfAdmin.won(resStats.month_revenue);
    document.getElementById('s-month-ppl').textContent='이번 달 '+(resStats.month_people??0)+'명';
    document.getElementById('s-pending').textContent=(resStats.pending_total??0)+'건';
    document.getElementById('s-pending-sub').textContent=(resStats.pending_people??0)+'명 · '+SurfAdmin.won(resStats.pending_amount);
    document.getElementById('s-intents').textContent=(intents||[]).length+'건';

    const alerts=[];
    if((resStats.pending_total??0)>0) alerts.push(`<a class="ops-alert ops-alert--pending" href="/availability/admin"><b>입금대기 ${resStats.pending_total}건</b><span>${SurfAdmin.won(resStats.pending_amount)} 확인 필요</span></a>`);
    if((intents||[]).length>0) alerts.push(`<button class="ops-alert" type="button" onclick="openCard('intents')"><b>예약문의 ${intents.length}건</b><span>최근 문의를 확인하세요</span></button>`);
    document.getElementById('ops-alerts').innerHTML=alerts.length?alerts.join(''):'<div class="sf-empty">지금 처리할 항목이 없습니다.</div>';

    const todayRows=todayReservations(resList);
    document.getElementById('today-timeline').innerHTML=todayRows.length?todayRows.map(r=>{
      const status=r.status||'예약';
      const cls=timelineStatusClass(status);
      return `<div class="timeline-row">
        <div class="timeline-time">${SurfAdmin.esc(r.time_slot||'-')}</div>
        <div class="timeline-main"><b>${SurfAdmin.esc(r.customer_name||'(이름없음)')}</b><span>${SurfAdmin.esc(r.program||'기타')} · ${Number(r.people)||0}명</span></div>
        <span class="sf-status ${cls}">${SurfAdmin.esc(status)}</span>
      </div>`;
    }).join(''):'<div class="sf-empty">오늘 예약이 없습니다.</div>';

    const it=document.getElementById('intents');
    it.innerHTML=intents.length?intents.map(r=>{
      const memo=r.admin_memo||'';
      return `
      <div class="item" id="intent-${r.id}">
        <div class="head">
          <span class="tag">예약문의</span><span class="time">${fmt(r.created_at)}</span><span class="uid">${uid(r.user_id)}</span>
          <span class="spacer"></span>
          <button class="memobtn" onclick="editMemo(${r.id})">📝 메모</button>
          <span class="arrow clickable" style="cursor:pointer" data-user-id="${attr(r.user_id)}" onclick="openUserFromElement(this)">›</span>
        </div>
        <div class="q clickable" style="cursor:pointer" data-user-id="${attr(r.user_id)}" onclick="openUserFromElement(this)">${esc(r.user_message)}</div>
        <div class="memo-slot">${memo?`<div class="memo-view"><b>📝 메모:</b> ${esc(memo)}</div>`:''}</div>
      </div>`;
    }).join(''):'<div class="empty">아직 예약 의향 고객이 없습니다.</div>';
    window._intentMemo={};
    intents.forEach(r=>window._intentMemo[r.id]=r.admin_memo||'');

    const cv=document.getElementById('convos');
    cv.innerHTML=convos.length?convos.map(r=>`
      <div class="item clickable" data-user-id="${attr(r.user_id)}" onclick="openUserFromElement(this)">
        <div class="head">
          <span class="time">${fmt(r.created_at)}</span><span class="uid">${uid(r.user_id)}</span>
          <span class="spacer"></span>
          <button class="delrowbtn" onclick="event.stopPropagation(); delTurn(${r.id})" title="대화 삭제">🗑</button>
          <span class="arrow">›</span>
        </div>
        <div class="q">Q. ${esc(r.user_message)}</div>
        <div class="a">A. ${esc(r.bot_reply)}</div>
      </div>`).join(''):'<div class="empty">아직 대화 기록이 없습니다.</div>';
  } catch(e){ console.error(e); }
}

let currentUserId=null;

async function openUser(userId){
  currentUserId=userId;
  document.getElementById('m-uid').textContent='ID: '+userId;
  document.getElementById('m-body').innerHTML='<div class="empty">불러오는 중...</div>';
  document.getElementById('modal').classList.add('show');
  await renderUser();
}

function openUserFromElement(el){
  const userId = el && el.dataset ? el.dataset.userId : '';
  if(userId) openUser(userId);
}

async function renderUser(){
  try {
    const rows=await fetch('api/user?user_id='+encodeURIComponent(currentUserId)).then(r=>r.json());
    const body=document.getElementById('m-body');
    if(!rows.length){ body.innerHTML='<div class="empty">대화 기록이 없습니다.</div>'; return; }
    body.innerHTML=rows.map(r=>`
      <div class="turn" id="turn-${r.id}">
        <div class="ts">${fmt(r.created_at)}${r.is_booking_intent?'<span class="booking">예약문의</span>':''}
          <span class="tools">
            <button class="tbtn" onclick="editTurn(${r.id})" title="수정">✏️</button>
            <button class="tbtn" onclick="delTurn(${r.id})" title="삭제">🗑</button>
          </span>
        </div>
        <div class="view">
          <div class="who">손님</div>
          <div class="bubble user">${esc(r.user_message)}</div>
          <div class="who" style="margin-top:8px;">AI 응답</div>
          <div class="bubble bot">${esc(r.bot_reply)}</div>
        </div>
      </div>`).join('');
    window._convRows={};
    rows.forEach(r=>window._convRows[r.id]=r);
  } catch(e){
    document.getElementById('m-body').innerHTML='<div class="empty">불러오기 실패</div>';
  }
}

function editTurn(id){
  const r=window._convRows[id];
  const turn=document.getElementById('turn-'+id);
  if(!r||!turn) return;
  turn.querySelector('.view').innerHTML=`
    <div class="editrow"><label>손님 메시지</label>
      <textarea id="ed-u-${id}" rows="2">${esc(r.user_message)}</textarea></div>
    <div class="editrow"><label>AI 응답</label>
      <textarea id="ed-b-${id}" rows="4">${esc(r.bot_reply)}</textarea></div>
    <div class="savebar">
      <button class="cancel" onclick="renderUser()">취소</button>
      <button class="ok" onclick="saveTurn(${id})">저장</button>
    </div>`;
}

async function saveTurn(id){
  const fd=new FormData();
  fd.append('id',id);
  fd.append('user_message',document.getElementById('ed-u-'+id).value);
  fd.append('bot_reply',document.getElementById('ed-b-'+id).value);
  await fetch('api/conversation/update',{method:'POST',body:fd});
  await renderUser();
  loadAll();
}

async function delTurn(id){
  if(!confirm('이 대화 1건을 삭제할까요?')) return;
  const fd=new FormData();
  fd.append('id',id);
  await fetch('api/conversation/delete',{method:'POST',body:fd});
  if(currentUserId){
    await renderUser();
  }
  loadAll();
}

function closeUser(){ document.getElementById('modal').classList.remove('show'); }
function closeCard(){ document.getElementById('cardmodal').classList.remove('show'); }

function isToday(ts){
  if(!ts) return false;
  const opt={timeZone:'Asia/Seoul'};
  return new Date(ts).toLocaleDateString('ko-KR',opt)===new Date().toLocaleDateString('ko-KR',opt);
}
function convListHTML(rows){
  if(!rows.length) return '<div class="empty">대화가 없습니다.</div>';
  return rows.map(r=>`
    <div class="item clickable" data-user-id="${attr(r.user_id)}" onclick="closeCard();openUserFromElement(this)">
      <div class="head">
        <span class="time">${fmt(r.created_at)}</span><span class="uid">${uid(r.user_id)}</span>
        <span class="spacer"></span>
        <button class="delrowbtn" onclick="event.stopPropagation(); delTurn(${r.id})" title="대화 삭제">🗑</button>
        <span class="arrow">›</span>
      </div>
      <div class="q">Q. ${esc(r.user_message)}</div>
      <div class="a">A. ${esc(r.bot_reply)}</div>
    </div>`).join('');
}
function resRowHTML(r){
  const d=(r.slot_date||'').slice(5);
  const meta=[r.platform,r.payment_method,r.memo].filter(Boolean).map(esc).join(' · ');
  const amt=Number(r.amount)||0;
  return `<div class="resrow">
    <div class="d"><div class="dd">${esc(d)||'-'}</div><div class="tt">${esc(r.time_slot)||''}</div></div>
    <div class="c"><div class="nm">${esc(r.customer_name)||'(이름없음)'} · ${esc(r.program)}</div>${meta?`<div class="mt">${meta}</div>`:''}</div>
    <div class="r"><div class="pp">${r.people}명</div>${amt>0?`<div class="am">${won(amt)}</div>`:''}</div>
  </div>`;
}

function openCard(type){
  const title=document.getElementById('cm-title');
  const body=document.getElementById('cm-body');
  const convos=window._convosAll||[];
  const intents=window._intentsAll||[];
  const rs=window._resStats||{};
  const list=window._resList||[];
  if(type==='intents'){
    title.textContent='🔔 예약 의향 고객 ('+intents.length+'건)';
    body.innerHTML=intents.length?intents.map(r=>{
      const memo=r.admin_memo||'';
      return `
        <div class="item" id="modal-intent-${r.id}">
          <div class="head">
            <span class="tag">예약문의</span><span class="time">${fmt(r.created_at)}</span><span class="uid">${uid(r.user_id)}</span>
            <span class="spacer"></span>
            <button class="memobtn" onclick="closeCard(); editMemo(${r.id})">📝 메모</button>
            <span class="arrow clickable" style="cursor:pointer" data-user-id="${attr(r.user_id)}" onclick="closeCard(); openUserFromElement(this)">›</span>
          </div>
          <div class="q clickable" style="cursor:pointer" data-user-id="${attr(r.user_id)}" onclick="closeCard(); openUserFromElement(this)">${esc(r.user_message)}</div>
          <div class="memo-slot">${memo?`<div class="memo-view"><b>📝 메모:</b> ${esc(memo)}</div>`:''}</div>
        </div>`;
    }).join(''):'<div class="empty">아직 예약 의향 고객이 없습니다.</div>';
  } else if(type==='today-reservations'){
    const todayRows=todayReservations(list);
    title.textContent='📅 오늘 예약';
    body.innerHTML=`
      <div class="revbox">
        <div class="b"><div class="k">예약 건수</div><div class="v">${rs.today_reservations||0}건</div></div>
        <div class="b"><div class="k">방문 인원</div><div class="v">${rs.today_people||0}명</div></div>
        <div class="b hi"><div class="k">예상 매출</div><div class="v">${won(rs.today_revenue)}</div></div>
      </div>
      `+(todayRows.length?todayRows.map(resRowHTML).join(''):'<div class="empty">오늘 예약이 없습니다.</div>');
  } else if(type==='total'){
    title.textContent='💬 전체 문의 ('+convos.length+'건)';
    body.innerHTML=convListHTML(convos);
  } else if(type==='today'){
    const t=convos.filter(r=>isToday(r.created_at));
    title.textContent='📅 오늘 문의 ('+t.length+'건)';
    body.innerHTML=convListHTML(t);
  } else if(type==='confirmed'){
    title.textContent='✅ 예약 확정 고객';
    const c=list.filter(r=>(r.status||'예약')==='예약');
    body.innerHTML=`
      <div class="revbox">
        <div class="b"><div class="k">오늘 예약</div><div class="v">${rs.today_reservations||0}건</div></div>
        <div class="b"><div class="k">이번 달</div><div class="v">${rs.month_reservations||0}건</div></div>
        <div class="b"><div class="k">누적 인원</div><div class="v">${rs.total_people||0}명</div></div>
      </div>`+(c.length?c.map(resRowHTML).join(''):'<div class="empty">확정된 예약이 없습니다.</div>');
  } else if(type==='revenue'){
    title.textContent='💰 수입 관리';
    const c=list.filter(r=>(r.status||'예약')==='예약');
    body.innerHTML=`
      <div class="revbox">
        <div class="b"><div class="k">오늘</div><div class="v">${won(rs.today_revenue)}</div></div>
        <div class="b hi"><div class="k">이번 달</div><div class="v">${won(rs.month_revenue)}</div></div>
        <div class="b"><div class="k">전체 누적</div><div class="v">${won(rs.total_revenue)}</div></div>
      </div>
      <div style="color:var(--sub);font-size:13px;margin-bottom:12px;">예약별 실수령 금액입니다. 금액 수정은 📅 예약 화면에서 합니다.</div>
      `+(c.length?c.map(resRowHTML).join(''):'<div class="empty">확정 수입 건이 없습니다.</div>');
  } else if(type==='pending'){
    const pd=list.filter(r=>(r.status||'예약')==='입금대기');
    title.textContent='⏳ 입금대기 (가예약)';
    body.innerHTML=`
      <div class="revbox">
        <div class="b"><div class="k">대기 건수</div><div class="v">${rs.pending_total||0}건</div></div>
        <div class="b"><div class="k">대기 인원</div><div class="v">${rs.pending_people||0}명</div></div>
        <div class="b hi"><div class="k">대기 금액</div><div class="v">${won(rs.pending_amount)}</div></div>
      </div>
      <div style="color:var(--sub);font-size:13px;margin-bottom:12px;">자리는 잡아뒀지만 아직 입금 확인 전입니다. 입금 확인되면 📅 예약 화면에서 ✅를 눌러 확정하세요.</div>
      `+(pd.length?pd.map(resRowHTML).join(''):'<div class="empty">입금대기 건이 없습니다.</div>');
  }
  document.getElementById('cardmodal').classList.add('show');
}

document.addEventListener('keydown',e=>{ if(e.key==='Escape'){ closeUser(); closeCard(); } });

function editMemo(id){
  const cur=(window._intentMemo&&window._intentMemo[id])||'';
  const slot=document.querySelector('#intent-'+id+' .memo-slot');
  if(!slot) return;
  slot.innerHTML=`
    <div class="memo-edit">
      <textarea id="memo-${id}" rows="2" placeholder="예: 6/7 데패강 4명 전화함 / 입금대기">${esc(cur)}</textarea>
      <div class="bar">
        <button class="cancel" onclick="loadAll()">취소</button>
        <button class="ok" onclick="saveMemo(${id})">메모 저장</button>
      </div>
    </div>`;
  document.getElementById('memo-'+id).focus();
}

async function saveMemo(id){
  const fd=new FormData();
  fd.append('id',id);
  fd.append('memo',document.getElementById('memo-'+id).value);
  await fetch('api/conversation/memo',{method:'POST',body:fd});
  loadAll();
}

loadAll();
setInterval(loadAll,30000);
</script>
<script>
SurfAdmin.initTheme('themebtn');
document.getElementById('themebtn').addEventListener('click', function(){
  if(window._resList) buildCharts(window._resList);
});
</script>
<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js');</script>
</body>
</html>"""
