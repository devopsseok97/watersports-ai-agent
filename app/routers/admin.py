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

CSS_VER = "20260826-navfix"


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
    return HTMLResponse(DASHBOARD_HTML.replace("{CSS_VER}", CSS_VER))


LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#0b2835">
<title>서퍼스트 관리자 로그인</title>
<link rel="stylesheet" href="/static/admin/surf-admin.css?v=""" + CSS_VER + """">
</head>
<body class="sf-login">
<main class="sf-login-card">
  <div class="sf-login-brand">
    서퍼스트<small>운영 콘솔</small>
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
<meta name="theme-color" content="#f2f6f8" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#06131a" media="(prefers-color-scheme: dark)">
<link rel="manifest" href="/static/manifest.json">
<link rel="apple-touch-icon" href="/static/icon-192.png">
<link rel="stylesheet" href="/static/admin/surf-admin.css?v={CSS_VER}">
<title>서퍼스트 · 오늘 운영</title>
<style>
  /* 홈 전용: 대화 리스트/모달/메모. surf-admin.css에 흡수하지 않은 세부만 유지 */
  .home-list { display: grid; gap: 6px; }
  .home-item {
    background: transparent;
    border: 0;
    padding: 10px 0;
    border-bottom: 1px solid var(--sf-line-soft);
    text-align: left;
    width: 100%;
    cursor: pointer;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 6px 10px;
    color: inherit;
  }
  .home-item:last-child { border-bottom: 0; }
  .home-item__head {
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    color: var(--sf-muted); font-size: 11px; font-weight: 700;
    grid-column: 1 / -1;
  }
  .home-item__tag {
    background: var(--sf-yellow); color: #4d3200;
    padding: 2px 7px; border-radius: 6px;
    font-size: 10px; font-weight: 900;
    letter-spacing: 0.04em;
  }
  .home-item__q {
    font-size: 14px; font-weight: 700; color: var(--sf-ink);
    overflow: hidden; display: -webkit-box;
    -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  }
  .home-item__a { color: var(--sf-muted); font-size: 12px; overflow: hidden;
    display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; }
  .home-item__memo {
    grid-column: 1 / -1;
    margin-top: 4px; padding: 6px 8px;
    background: var(--sf-yellow-soft);
    border: 1px solid color-mix(in srgb, var(--sf-yellow) 30%, transparent);
    border-radius: 6px;
    font-size: 12px; color: var(--sf-ink);
    white-space: pre-wrap; word-break: break-word;
  }
  .home-item__actions { display: flex; gap: 4px; }
  .home-item__actions button {
    color: var(--sf-muted); font-size: 15px;
    padding: 4px 8px; min-width: 36px; min-height: 36px;
    border-radius: 6px;
  }
  .home-item__actions button:hover { background: var(--sf-field); color: var(--sf-ink); }

  /* 모달: 손님 상세 대화 */
  .conv-turn { margin-bottom: 16px; }
  .conv-turn .ts { color: var(--sf-muted); font-size: 12px; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
  .conv-turn .booking {
    background: var(--sf-yellow); color: #4d3200;
    font-size: 10px; font-weight: 900; padding: 2px 7px; border-radius: 6px;
  }
  .conv-turn .tools { margin-left: auto; display: flex; gap: 4px; }
  .conv-turn .tbtn {
    background: transparent; border: 1px solid var(--sf-line-soft);
    color: var(--sf-muted); border-radius: 8px; padding: 5px 10px;
    min-width: 36px; min-height: 36px; font-size: 13px;
  }
  .conv-turn .tbtn:hover { color: var(--sf-ink); background: var(--sf-field); }
  .conv-turn .who { font-size: 12px; font-weight: 800; color: var(--sf-muted); margin-bottom: 4px; }
  .bubble {
    padding: 10px 14px; border-radius: 14px; font-size: 14px; line-height: 1.5;
    white-space: pre-wrap; word-break: break-word;
  }
  .bubble.user {
    background: color-mix(in srgb, var(--sf-river) 12%, var(--sf-surface));
    color: var(--sf-ink);
    border-radius: 14px 14px 14px 4px;
  }
  .bubble.bot {
    background: var(--sf-field);
    border: 1px solid var(--sf-line-soft);
    margin-top: 6px;
    border-radius: 14px 14px 4px 14px;
  }
  .conv-turn textarea {
    width: 100%; background: var(--sf-field); border: 1px solid var(--sf-line);
    border-radius: 10px; padding: 10px; font-size: 14px; font-family: inherit;
    line-height: 1.5; resize: vertical; min-height: 60px;
  }
  .conv-turn .savebar { display: flex; gap: 8px; margin-top: 8px; }
  .conv-turn .savebar button { flex: 1; }

  .memo-edit { margin-top: 6px; grid-column: 1 / -1; }
  .memo-edit textarea {
    width: 100%; background: var(--sf-field); border: 1px solid var(--sf-line);
    border-radius: 8px; padding: 8px 10px; font-size: 13px;
    font-family: inherit; line-height: 1.5; resize: vertical; min-height: 44px;
  }
  .memo-edit .bar { display: flex; gap: 6px; margin-top: 6px; }
  .memo-edit .bar button { flex: 1; }

  /* 아이콘 헬퍼 */
  .icon { width: 20px; height: 20px; stroke: currentColor; fill: none; stroke-width: 1.8;
          stroke-linecap: round; stroke-linejoin: round; }
</style>
<script src="/static/admin/surf-admin.js"></script>
</head>
<body>
<div class="sf-app">
  <aside class="sf-sidebar">
    <div class="sf-brand">서퍼스트<small>운영 콘솔</small></div>
    <nav class="sf-nav" aria-label="관리자 메뉴">
      <a class="sf-nav__link" href="/admin/" aria-current="page">
        <svg class="sf-nav__icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h5v-6h4v6h5V10"/></svg>
        <span>홈</span>
      </a>
      <a class="sf-nav__link" href="/availability/admin">
        <svg class="sf-nav__icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>
        <span>예약</span>
      </a>
      <a class="sf-nav__link" href="/photos/admin">
        <svg class="sf-nav__icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="18" height="14" rx="2"/><circle cx="12" cy="13" r="4"/><path d="M8 6l1.5-2h5L16 6"/></svg>
        <span>사진</span>
      </a>
      <a class="sf-nav__link" href="/dashboard/">
        <svg class="sf-nav__icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>
        <span>분석</span>
      </a>
    </nav>
  </aside>
  <div class="sf-main">
    <header class="sf-topbar">
      <div class="sf-topbar__title">오늘 운영</div>
      <div class="sf-actions">
        <button class="sf-icon-btn" id="themebtn" type="button" aria-label="테마 전환">
          <svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 109 9 7 7 0 01-9-9z"/></svg>
        </button>
        <button class="sf-icon-btn" onclick="loadAll()" type="button" aria-label="새로고침">
          <svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 0115.5-6.3L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 01-15.5 6.3L3 16"/><path d="M3 21v-5h5"/></svg>
        </button>
        <a class="sf-btn sf-btn--sm sf-btn--ghost" href="/admin/logout">로그아웃</a>
      </div>
    </header>
    <main class="sf-page">
      <div class="sf-page-head">
        <div>
          <h1 class="sf-page-title">현장 상태</h1>
          <p class="sf-page-sub" id="today-label">오늘 방문·입금대기·문의를 확인하세요.</p>
        </div>
        <div class="sf-actions">
          <a class="sf-btn sf-btn--primary" href="/availability/admin">＋ 예약 추가</a>
        </div>
      </div>

      <div id="ops-alerts" class="ops-alerts" style="margin-bottom:12px;"></div>

      <div class="sf-card-grid">
        <button class="sf-metric sf-metric--clickable sf-metric--hero" type="button" onclick="openCard('today-reservations')">
          <div class="sf-metric__label">오늘 방문</div>
          <div class="sf-metric__value" id="s-today-ppl">-</div>
          <div class="sf-metric__note" id="s-today-rev">-</div>
        </button>
        <button class="sf-metric sf-metric--clickable sf-metric--attention" type="button" onclick="openCard('pending')">
          <div class="sf-metric__label">입금대기</div>
          <div class="sf-metric__value" id="s-pending">-</div>
          <div class="sf-metric__note" id="s-pending-sub">-</div>
        </button>
        <button class="sf-metric sf-metric--clickable sf-metric--signal" type="button" onclick="openCard('intents')">
          <div class="sf-metric__label">예약문의</div>
          <div class="sf-metric__value" id="s-intents">-</div>
          <div class="sf-metric__note">최근 7일</div>
        </button>
        <button class="sf-metric sf-metric--clickable sf-metric--money" type="button" onclick="openCard('revenue')">
          <div class="sf-metric__label">이번 달 수입</div>
          <div class="sf-metric__value money" id="s-revenue">-</div>
          <div class="sf-metric__note" id="s-month-ppl">-</div>
        </button>
      </div>

      <div class="ops-layout">
        <section class="sf-panel">
          <div class="panel-headline">
            <h2 class="sf-section-title">오늘 예약 타임라인</h2>
            <a class="sf-btn sf-btn--sm sf-btn--ghost" href="/availability/admin">전체 →</a>
          </div>
          <div id="today-timeline" class="timeline-list"><div class="sf-empty">불러오는 중…</div></div>
        </section>
        <section class="sf-panel">
          <div class="panel-headline">
            <h2 class="sf-section-title">예약 의향 고객</h2>
            <span class="sf-status sf-status--muted" id="intents-count">-</span>
          </div>
          <div id="intents" class="home-list"><div class="sf-empty">불러오는 중…</div></div>
        </section>
        <section class="sf-panel">
          <div class="panel-headline">
            <h2 class="sf-section-title">최근 대화</h2>
            <button class="sf-btn sf-btn--sm sf-btn--ghost" type="button" onclick="openCard('total')">전체 보기</button>
          </div>
          <div id="convos" class="home-list"><div class="sf-empty">불러오는 중…</div></div>
        </section>
      </div>
    </main>
  </div>
</div>

<div class="modal-bg" id="modal" onclick="if(event.target===this)closeUser()">
  <div class="modal">
    <div class="modal-head">
      <div>
        <div class="t" style="font-weight:900;font-size:15px;">고객 대화 상세</div>
        <div class="u" id="m-uid" style="color:var(--sf-muted);font-size:12px;font-family:monospace;margin-top:2px;"></div>
      </div>
      <button class="sf-icon-btn" onclick="closeUser()" aria-label="닫기" style="border-color:var(--sf-line);">✕</button>
    </div>
    <div class="modal-body" id="m-body"></div>
  </div>
</div>

<div class="modal-bg" id="cardmodal" onclick="if(event.target===this)closeCard()">
  <div class="modal">
    <div class="modal-head">
      <div><div class="t" id="cm-title" style="font-weight:900;font-size:15px;">상세</div></div>
      <button class="sf-icon-btn" onclick="closeCard()" aria-label="닫기" style="border-color:var(--sf-line);">✕</button>
    </div>
    <div class="modal-body" id="cm-body"></div>
  </div>
</div>

<script>
const INTENT_TTL_DAYS = 7;

function fmt(ts){ if(!ts)return'-'; const d=new Date(ts); return d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function attr(s){ return esc(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function uid(s){ return s?esc(String(s).slice(0,8))+'…':'-'; }
function won(n){ return (Number(n)||0).toLocaleString('ko-KR')+'원'; }
function todayKey(){
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const out={}; parts.forEach(p=>{ if(p.type!=='literal') out[p.type]=p.value; });
  return (out.year||'')+'-'+(out.month||'')+'-'+(out.day||'');
}
function timelineStatusClass(status){
  if(status==='예약') return 'sf-status--ok';
  if(status==='입금대기') return 'sf-status--pending';
  if(status==='노쇼') return 'sf-status--danger';
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
    const [rawIntents, rawConvos, resStats, rawResList] = await Promise.all([
      fetch('api/intents').then(r=>r.json()),
      fetch('api/conversations').then(r=>r.json()),
      fetch('api/reservation-stats').then(r=>r.json()),
      fetch('api/reservations').then(r=>r.json()),
    ]);
    const intents = freshBookingIntents(rawIntents);
    const convos = Array.isArray(rawConvos) ? rawConvos : [];
    const resList = Array.isArray(rawResList) ? rawResList : [];
    window._convosAll = convos;
    window._intentsAll = intents;
    window._resStats = resStats || {};
    window._resList = resList;

    document.getElementById('today-label').textContent = SurfAdmin.todayLabel() + ' 기준';
    document.getElementById('s-today-ppl').textContent = (resStats.today_people ?? 0) + '명';
    document.getElementById('s-today-rev').textContent = won(resStats.today_revenue) + ' 예상';
    document.getElementById('s-revenue').textContent = won(resStats.month_revenue);
    document.getElementById('s-month-ppl').textContent = '이번 달 ' + (resStats.month_people ?? 0) + '명';
    document.getElementById('s-pending').textContent = (resStats.pending_total ?? 0) + '건';
    document.getElementById('s-pending-sub').textContent = (resStats.pending_people ?? 0) + '명 · ' + won(resStats.pending_amount);
    document.getElementById('s-intents').textContent = intents.length + '건';
    document.getElementById('intents-count').textContent = intents.length + '건';

    const alerts = [];
    if ((resStats.pending_total ?? 0) > 0) {
      alerts.push(`<a class="ops-alert ops-alert--pending" href="/availability/admin"><div><b>입금대기 ${resStats.pending_total}건</b><span>${won(resStats.pending_amount)} 확인 필요</span></div><span class="ops-alert__arrow">›</span></a>`);
    }
    if (intents.length > 0) {
      alerts.push(`<button class="ops-alert ops-alert--info" type="button" onclick="openCard('intents')"><div><b>예약문의 ${intents.length}건</b><span>최근 7일 문의를 확인하세요</span></div><span class="ops-alert__arrow">›</span></button>`);
    }
    document.getElementById('ops-alerts').innerHTML = alerts.join('');

    const todayRows = todayReservations(resList);
    document.getElementById('today-timeline').innerHTML = todayRows.length ? todayRows.map(r=>{
      const status = r.status || '예약';
      const cls = timelineStatusClass(status);
      return `<div class="timeline-row">
        <div class="timeline-time">${esc(r.time_slot||'-')}</div>
        <div class="timeline-main"><b>${esc(r.customer_name||'(이름없음)')}</b><span>${esc(r.program||'기타')} · ${Number(r.people)||0}명</span></div>
        <span class="sf-status ${cls}">${esc(status)}</span>
      </div>`;
    }).join('') : '<div class="sf-empty">오늘 예약이 없습니다.</div>';

    const it = document.getElementById('intents');
    it.innerHTML = intents.length ? intents.map(r=>{
      const memo = r.admin_memo || '';
      return `
      <div class="home-item" id="intent-${r.id}">
        <div class="home-item__head">
          <span class="home-item__tag">예약문의</span>
          <span>${fmt(r.created_at)}</span>
          <span style="font-family:monospace">${uid(r.user_id)}</span>
        </div>
        <div class="home-item__q clickable" style="cursor:pointer" data-user-id="${attr(r.user_id)}" onclick="openUserFromElement(this)">${esc(r.user_message)}</div>
        <div class="home-item__actions">
          <button type="button" onclick="event.stopPropagation(); editMemo(${r.id})" aria-label="메모">📝</button>
          <button type="button" data-user-id="${attr(r.user_id)}" onclick="event.stopPropagation(); openUserFromElement(this)" aria-label="대화 열기">›</button>
        </div>
        <div class="memo-slot">${memo ? `<div class="home-item__memo"><b>메모</b> · ${esc(memo)}</div>` : ''}</div>
      </div>`;
    }).join('') : '<div class="sf-empty">최근 예약문의가 없습니다.</div>';

    window._intentMemo = {};
    intents.forEach(r=>{ window._intentMemo[r.id] = r.admin_memo || ''; });

    const cv = document.getElementById('convos');
    const preview = convos.slice(0, 8);
    cv.innerHTML = preview.length ? preview.map(r=>`
      <button class="home-item" type="button" data-user-id="${attr(r.user_id)}" onclick="openUserFromElement(this)">
        <div class="home-item__head">
          <span>${fmt(r.created_at)}</span>
          <span style="font-family:monospace">${uid(r.user_id)}</span>
        </div>
        <div class="home-item__q">${esc(r.user_message)}</div>
        <div class="home-item__actions">
          <span style="color:var(--sf-muted);font-weight:900;">›</span>
        </div>
        <div class="home-item__a" style="grid-column:1/-1">${esc(r.bot_reply)}</div>
      </button>`).join('') : '<div class="sf-empty">아직 대화가 없습니다.</div>';
  } catch (e) { console.error(e); }
}

let currentUserId = null;

async function openUser(userId){
  currentUserId = userId;
  document.getElementById('m-uid').textContent = 'ID · ' + userId;
  document.getElementById('m-body').innerHTML = '<div class="sf-empty">불러오는 중…</div>';
  document.getElementById('modal').classList.add('show');
  await renderUser();
}

function openUserFromElement(el){
  const userId = el && el.dataset ? el.dataset.userId : '';
  if (userId) openUser(userId);
}

async function renderUser(){
  try {
    const rows = await fetch('api/user?user_id=' + encodeURIComponent(currentUserId)).then(r=>r.json());
    const body = document.getElementById('m-body');
    if (!rows.length) { body.innerHTML = '<div class="sf-empty">대화 기록이 없습니다.</div>'; return; }
    body.innerHTML = rows.map(r=>`
      <div class="conv-turn" id="turn-${r.id}">
        <div class="ts">
          ${fmt(r.created_at)}${r.is_booking_intent ? '<span class="booking">예약문의</span>' : ''}
          <span class="tools">
            <button class="tbtn" onclick="editTurn(${r.id})" title="수정">수정</button>
            <button class="tbtn" onclick="delTurn(${r.id})" title="삭제">삭제</button>
          </span>
        </div>
        <div class="view">
          <div class="who">손님</div>
          <div class="bubble user">${esc(r.user_message)}</div>
          <div class="who" style="margin-top:8px;">AI 응답</div>
          <div class="bubble bot">${esc(r.bot_reply)}</div>
        </div>
      </div>`).join('');
    window._convRows = {};
    rows.forEach(r=>{ window._convRows[r.id] = r; });
  } catch (e) {
    document.getElementById('m-body').innerHTML = '<div class="sf-empty">불러오기 실패</div>';
  }
}

function editTurn(id){
  const r = window._convRows[id];
  const turn = document.getElementById('turn-' + id);
  if (!r || !turn) return;
  turn.querySelector('.view').innerHTML = `
    <div class="who">손님 메시지</div>
    <textarea id="ed-u-${id}" rows="2">${esc(r.user_message)}</textarea>
    <div class="who" style="margin-top:8px;">AI 응답</div>
    <textarea id="ed-b-${id}" rows="4">${esc(r.bot_reply)}</textarea>
    <div class="savebar">
      <button class="sf-btn sf-btn--sm" onclick="renderUser()">취소</button>
      <button class="sf-btn sf-btn--sm sf-btn--primary" onclick="saveTurn(${id})">저장</button>
    </div>`;
}

async function saveTurn(id){
  const fd = new FormData();
  fd.append('id', id);
  fd.append('user_message', document.getElementById('ed-u-' + id).value);
  fd.append('bot_reply', document.getElementById('ed-b-' + id).value);
  await fetch('api/conversation/update', { method: 'POST', body: fd });
  await renderUser();
  loadAll();
}

async function delTurn(id){
  if (!confirm('이 대화 1건을 삭제할까요?')) return;
  const fd = new FormData();
  fd.append('id', id);
  await fetch('api/conversation/delete', { method: 'POST', body: fd });
  if (currentUserId) await renderUser();
  loadAll();
}

function closeUser(){ document.getElementById('modal').classList.remove('show'); }
function closeCard(){ document.getElementById('cardmodal').classList.remove('show'); }

function isToday(ts){
  if (!ts) return false;
  const opt = { timeZone: 'Asia/Seoul' };
  return new Date(ts).toLocaleDateString('ko-KR', opt) === new Date().toLocaleDateString('ko-KR', opt);
}
function convListHTML(rows){
  if (!rows.length) return '<div class="sf-empty">대화가 없습니다.</div>';
  return rows.map(r=>`
    <button class="home-item" type="button" data-user-id="${attr(r.user_id)}" onclick="closeCard();openUserFromElement(this)">
      <div class="home-item__head">
        <span>${fmt(r.created_at)}</span><span style="font-family:monospace">${uid(r.user_id)}</span>
      </div>
      <div class="home-item__q">${esc(r.user_message)}</div>
      <div class="home-item__actions"><span style="color:var(--sf-muted);font-weight:900;">›</span></div>
      <div class="home-item__a" style="grid-column:1/-1">${esc(r.bot_reply)}</div>
    </button>`).join('');
}
function resRowHTML(r){
  const d = (r.slot_date || '').slice(5);
  const meta = [r.platform, r.payment_method, r.memo].filter(Boolean).map(esc).join(' · ');
  const amt = Number(r.amount) || 0;
  return `<div class="res-row"><div class="res-main">
    <div class="r-time">${esc(r.time_slot) || '-'}</div>
    <div><div class="r-name">${esc(r.customer_name) || '(이름없음)'} · ${esc(r.program)}</div>
      <div class="r-meta">${esc(d)}${meta ? ' · ' + meta : ''}</div></div>
    <div style="text-align:right;">
      <div style="font-weight:900;">${r.people}명</div>
      ${amt > 0 ? `<div style="color:var(--sf-green);font-weight:800;font-size:12px;margin-top:2px;">${won(amt)}</div>` : ''}
    </div>
  </div></div>`;
}

function openCard(type){
  const title = document.getElementById('cm-title');
  const body = document.getElementById('cm-body');
  const convos = window._convosAll || [];
  const intents = window._intentsAll || [];
  const rs = window._resStats || {};
  const list = window._resList || [];
  const summary = (items) => `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;">${items.map(([k,v,hi])=>`<div style="background:${hi?'var(--sf-yellow-soft)':'var(--sf-field)'};border:1px solid ${hi?'color-mix(in srgb,var(--sf-yellow) 40%,transparent)':'var(--sf-line-soft)'};border-radius:10px;padding:10px;text-align:center;"><div style="color:var(--sf-muted);font-size:11px;font-weight:800;margin-bottom:4px;">${k}</div><div style="font-size:16px;font-weight:900;color:${hi?'#7a4900':'var(--sf-ink)'};">${v}</div></div>`).join('')}</div>`;

  if (type === 'intents') {
    title.textContent = '예약 의향 고객 · ' + intents.length + '건';
    body.innerHTML = intents.length ? intents.map(r=>{
      const memo = r.admin_memo || '';
      return `<div class="home-item" id="modal-intent-${r.id}" style="border-bottom:1px solid var(--sf-line-soft);padding:12px 0;">
        <div class="home-item__head"><span class="home-item__tag">예약문의</span><span>${fmt(r.created_at)}</span><span style="font-family:monospace">${uid(r.user_id)}</span></div>
        <div class="home-item__q clickable" style="cursor:pointer" data-user-id="${attr(r.user_id)}" onclick="closeCard(); openUserFromElement(this)">${esc(r.user_message)}</div>
        <div class="home-item__actions">
          <button type="button" onclick="closeCard(); editMemo(${r.id})">📝</button>
          <button type="button" data-user-id="${attr(r.user_id)}" onclick="closeCard(); openUserFromElement(this)">›</button>
        </div>
        <div class="memo-slot">${memo ? `<div class="home-item__memo"><b>메모</b> · ${esc(memo)}</div>` : ''}</div>
      </div>`;
    }).join('') : '<div class="sf-empty">아직 예약 의향 고객이 없습니다.</div>';
  } else if (type === 'today-reservations') {
    const todayRows = todayReservations(list);
    title.textContent = '오늘 예약';
    body.innerHTML = summary([['예약 건수', (rs.today_reservations||0)+'건'], ['방문 인원', (rs.today_people||0)+'명'], ['예상 매출', won(rs.today_revenue), true]])
      + (todayRows.length ? todayRows.map(resRowHTML).join('') : '<div class="sf-empty">오늘 예약이 없습니다.</div>');
  } else if (type === 'total') {
    title.textContent = '최근 대화 · ' + convos.length + '건';
    body.innerHTML = convListHTML(convos);
  } else if (type === 'today') {
    const t = convos.filter(r => isToday(r.created_at));
    title.textContent = '오늘 문의 · ' + t.length + '건';
    body.innerHTML = convListHTML(t);
  } else if (type === 'revenue') {
    title.textContent = '수입 관리';
    const c = list.filter(r => (r.status || '예약') === '예약');
    body.innerHTML = summary([['오늘', won(rs.today_revenue)], ['이번 달', won(rs.month_revenue), true], ['전체 누적', won(rs.total_revenue)]])
      + '<div style="color:var(--sf-muted);font-size:12px;margin-bottom:10px;">예약별 실수령 금액입니다. 금액 수정은 예약 화면에서 합니다.</div>'
      + (c.length ? c.map(resRowHTML).join('') : '<div class="sf-empty">확정 수입 건이 없습니다.</div>');
  } else if (type === 'pending') {
    const pd = list.filter(r => (r.status || '예약') === '입금대기');
    title.textContent = '입금대기 (가예약)';
    body.innerHTML = summary([['대기 건수', (rs.pending_total||0)+'건'], ['대기 인원', (rs.pending_people||0)+'명'], ['대기 금액', won(rs.pending_amount), true]])
      + '<div style="color:var(--sf-muted);font-size:12px;margin-bottom:10px;">자리는 잡아뒀지만 아직 입금 확인 전입니다. 입금 확인되면 예약 화면에서 확정하세요.</div>'
      + (pd.length ? pd.map(resRowHTML).join('') : '<div class="sf-empty">입금대기 건이 없습니다.</div>');
  }
  document.getElementById('cardmodal').classList.add('show');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeUser(); closeCard(); } });

function editMemo(id){
  const cur = (window._intentMemo && window._intentMemo[id]) || '';
  const slot = document.querySelector('#intent-' + id + ' .memo-slot');
  if (!slot) return;
  slot.innerHTML = `
    <div class="memo-edit">
      <textarea id="memo-${id}" rows="2" placeholder="예: 6/7 데패강 4명 전화함 / 입금대기">${esc(cur)}</textarea>
      <div class="bar">
        <button class="sf-btn sf-btn--sm" onclick="loadAll()">취소</button>
        <button class="sf-btn sf-btn--sm sf-btn--primary" onclick="saveMemo(${id})">메모 저장</button>
      </div>
    </div>`;
  document.getElementById('memo-' + id).focus();
}

async function saveMemo(id){
  const fd = new FormData();
  fd.append('id', id);
  fd.append('memo', document.getElementById('memo-' + id).value);
  await fetch('api/conversation/memo', { method: 'POST', body: fd });
  loadAll();
}

loadAll();
setInterval(loadAll, 30000);

SurfAdmin.initTheme('themebtn');
</script>
<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js');</script>
</body>
</html>"""
