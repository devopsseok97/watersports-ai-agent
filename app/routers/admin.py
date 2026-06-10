"""사장님용 웹 관리자 대시보드.

- GET /admin           → 대시보드 HTML
- GET /admin/api/stats → 요약 지표 (JSON)
- GET /admin/api/intents → 예약 의향 고객 (JSON)
- GET /admin/api/conversations → 최근 대화 기록 (JSON)

간단한 HTTP Basic 인증(아이디 무시, 비밀번호 = ADMIN_PASSWORD)으로 보호.
ADMIN_PASSWORD 미설정 시 인증을 건너뜀(개발용).
"""
import secrets
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings
from fastapi import Form
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
security = HTTPBasic(auto_error=False)


def require_admin(credentials: HTTPBasicCredentials | None = Depends(security)):
    """ADMIN_PASSWORD가 설정돼 있으면 비밀번호 검증."""
    password = getattr(settings, "admin_password", "") or ""
    if not password:
        return  # 개발 환경: 인증 스킵
    if credentials is None or not secrets.compare_digest(
        credentials.password, password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다.",
            headers={"WWW-Authenticate": "Basic"},
        )


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
        return await get_booking_intents(limit=100)
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
    """특정 고객의 전체 대화 흐름 (모달 상세보기용)"""
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
    """예약확정고객 수 + 수입 요약 (홈 통계 카드용)."""
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
    """최근 예약 건 목록 (예약확정고객/수입 상세보기용)."""
    try:
        return await av.get_recent_reservations(limit=200)
    except Exception as e:
        logger.error(f"예약 목록 조회 실패: {e}")
        return []


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard(_=Depends(require_admin)):
    return HTMLResponse(DASHBOARD_HTML)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>서퍼스트 관리자 · 홈</title>
<style>
  :root {
    --bg:#f4f6f9; --card:#ffffff; --line:#e2e8f0; --txt:#1a2129; --sub:#64748b;
    --accent:#2563eb; --accent-soft:#dbeafe; --green:#16a34a; --green-soft:#dcfce7;
    --warn:#d97706; --warn-soft:#fef3c7; --field:#f8fafc; --shadow:0 1px 3px rgba(0,0,0,.08);
  }
  [data-theme="dark"] {
    --bg:#0f1419; --card:#1a2129; --line:#2a3441; --txt:#e6edf3; --sub:#8b98a5;
    --accent:#2f81f7; --accent-soft:#16243a; --green:#3fb950; --green-soft:#13351c;
    --warn:#f0883e; --warn-soft:#3a2812; --field:#0f1419; --shadow:none;
  }
  * { box-sizing:border-box; }
  html { -webkit-text-size-adjust:100%; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
         background:var(--bg); color:var(--txt); font-size:17px; line-height:1.45; }

  /* ===== 공통 헤더 + 네비 ===== */
  header { background:var(--card); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:10; }
  .htop { padding:14px 18px; display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .brand { font-size:19px; font-weight:800; }
  .brand span { color:var(--sub); font-weight:600; font-size:14px; margin-left:4px; }
  .htools { display:flex; align-items:center; gap:8px; }
  .themebtn, .refresh { background:var(--field); border:1px solid var(--line); color:var(--txt);
              height:42px; border-radius:10px; cursor:pointer; font-size:15px; font-weight:600; }
  .themebtn { width:42px; font-size:20px; padding:0; }
  .refresh { padding:0 14px; }
  .refresh:active { background:var(--accent); color:#fff; }
  nav { display:flex; gap:6px; padding:0 12px 12px; overflow-x:auto; }
  nav a { flex:1; text-align:center; white-space:nowrap; text-decoration:none; color:var(--sub);
          font-size:16px; font-weight:700; padding:11px 10px; border-radius:10px; background:var(--field); border:1px solid var(--line); }
  nav a.active { color:#fff; background:var(--accent); border-color:var(--accent); }

  main { padding:18px; max-width:1000px; margin:0 auto; }

  /* ===== 통계 카드 ===== */
  .cards { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; margin-bottom:24px; }
  .stat { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:18px; box-shadow:var(--shadow); }
  .stat .label { color:var(--sub); font-size:15px; margin-bottom:10px; font-weight:600; }
  .stat .value { font-size:36px; font-weight:900; line-height:1; }
  .stat .value.money { font-size:27px; }
  .stat .sublabel { color:var(--sub); font-size:13px; margin-top:10px; font-weight:600; opacity:.85; }
  .stat.accent .value { color:var(--accent); }
  .stat.green { background:var(--green-soft); border-color:var(--green); }
  .stat.green .value { color:var(--green); }
  .stat.warn { background:var(--warn-soft); border-color:var(--warn); }
  .stat.warn .value { color:var(--warn); }
  .stat.danger { background:var(--full-bg, #fee2e2); border-color:var(--full, #dc2626); }
  .stat.danger .value { color:var(--full, #dc2626); }
  .stat.amber { background:rgba(245,158,11,.1); border-color:#f59e0b; }
  .stat.amber .value { color:#d97706; }
  .stat.clickable { cursor:pointer; transition:transform .1s, border-color .12s; }
  .stat.clickable:hover { border-color:var(--accent); }
  .stat.clickable:active { transform:scale(.98); }
  @media (min-width:760px){ .cards { grid-template-columns:repeat(6,1fr); } }

  /* ===== 카드 상세: 수입 요약 박스 ===== */
  .revbox { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:16px; }
  .revbox .b { background:var(--field); border:1px solid var(--line); border-radius:12px; padding:14px; text-align:center; }
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

  /* ===== 카드 리스트 (테이블 대체) ===== */
  .item { background:var(--card); border:1px solid var(--line); border-radius:14px;
          padding:16px; margin-bottom:10px; box-shadow:var(--shadow); }
  .item .head { display:flex; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap; }
  .item .time { color:var(--sub); font-size:14px; }
  .item .uid { color:var(--sub); font-family:monospace; font-size:13px; }
  .tag { display:inline-block; background:var(--warn); color:#fff; font-size:13px; font-weight:700; padding:3px 9px; border-radius:7px; }
  .item .q { font-size:17px; font-weight:600; }
  .item .a { color:var(--sub); font-size:16px; margin-top:6px; }
  .item.clickable { cursor:pointer; transition:border-color .12s; }
  .item.clickable:hover { border-color:var(--accent); }
  .item .arrow { color:var(--sub); font-size:18px; }
  .item .head .spacer { margin-left:auto; }
  .memobtn { background:var(--field); border:1px solid var(--line); color:var(--sub);
             border-radius:8px; font-size:14px; font-weight:700; cursor:pointer; padding:5px 10px; }
  .memobtn:active { color:var(--accent); }
  .memo-view { margin-top:10px; padding:10px 12px; background:var(--warn-soft); border:1px solid var(--warn);
               border-radius:10px; font-size:15px; color:var(--txt); white-space:pre-wrap; word-break:break-word; }
  .memo-view b { color:var(--warn); }
  .memo-edit { margin-top:10px; }
  .memo-edit textarea { width:100%; background:var(--field); border:1px solid var(--line); color:var(--txt);
              border-radius:10px; padding:10px 12px; font-size:15px; font-family:inherit; line-height:1.5; resize:vertical; }
  .memo-edit .bar { display:flex; gap:8px; margin-top:8px; }
  .memo-edit .bar button { flex:1; border:none; border-radius:10px; padding:11px; font-size:15px; font-weight:700; cursor:pointer; }
  .memo-edit .bar .ok { background:var(--accent); color:#fff; }
  .memo-edit .bar .cancel { background:var(--field); border:1px solid var(--line); color:var(--txt); }
  .empty { color:var(--sub); padding:28px; text-align:center; font-size:16px;
           background:var(--card); border:1px dashed var(--line); border-radius:14px; }

  /* ===== 고객 상세 모달 ===== */
  .modal-bg { position:fixed; inset:0; background:rgba(0,0,0,.5); display:none;
              align-items:flex-end; justify-content:center; z-index:100; }
  .modal-bg.show { display:flex; }
  .modal { background:var(--card); width:100%; max-width:640px; max-height:88vh;
           border-radius:18px 18px 0 0; display:flex; flex-direction:column; overflow:hidden; }
  .modal-head { padding:18px 20px; border-bottom:1px solid var(--line); display:flex;
                align-items:center; justify-content:space-between; gap:10px; }
  .modal-head .t { font-size:18px; font-weight:800; }
  .modal-head .u { color:var(--sub); font-size:13px; font-family:monospace; margin-top:3px; }
  .modal-head .x { background:var(--field); border:1px solid var(--line); color:var(--txt);
                   width:40px; height:40px; border-radius:10px; font-size:20px; cursor:pointer; }
  .modal-body { padding:16px 20px; overflow-y:auto; }
  .turn { margin-bottom:18px; }
  .turn .ts { color:var(--sub); font-size:13px; margin-bottom:6px; }
  .bubble { padding:11px 14px; border-radius:14px; font-size:16px; line-height:1.5; white-space:pre-wrap; word-break:break-word; }
  .bubble.user { background:var(--accent-soft); color:var(--txt); border-radius:14px 14px 14px 4px; }
  .bubble.bot { background:var(--field); border:1px solid var(--line); margin-top:6px; border-radius:14px 14px 4px 14px; }
  .turn .who { font-size:13px; font-weight:700; color:var(--sub); margin-bottom:4px; }
  .turn .booking { display:inline-block; background:var(--warn); color:#fff; font-size:12px; font-weight:700; padding:2px 8px; border-radius:6px; margin-left:6px; }
  .turn .tools { display:flex; gap:4px; margin-left:auto; }
  .turn .ts { display:flex; align-items:center; }
  .turn .tbtn { background:var(--field); border:1px solid var(--line); color:var(--sub);
                border-radius:8px; font-size:15px; cursor:pointer; padding:4px 8px; }
  .turn .tbtn:active { color:var(--accent); }
  .turn textarea { width:100%; background:var(--field); border:1px solid var(--line); color:var(--txt);
                   border-radius:10px; padding:10px 12px; font-size:15px; font-family:inherit; line-height:1.5; resize:vertical; }
  .turn .editrow { margin-top:8px; }
  .turn .editrow label { font-size:13px; font-weight:700; color:var(--sub); display:block; margin-bottom:4px; }
  .turn .savebar { display:flex; gap:8px; margin-top:10px; }
  .turn .savebar button { flex:1; border:none; border-radius:10px; padding:11px; font-size:15px; font-weight:700; cursor:pointer; }
  .turn .savebar .ok { background:var(--accent); color:#fff; }
  .turn .savebar .cancel { background:var(--field); border:1px solid var(--line); color:var(--txt); }
  @media (min-width:560px){ .modal-bg { align-items:center; } .modal { border-radius:18px; } }
</style>
</head>
<body>
<header>
  <div class="htop">
    <div class="brand">🏄 서퍼스트<span>관리자</span></div>
    <div class="htools">
      <button class="themebtn" id="themebtn" onclick="toggleTheme()" title="화면 톤 전환">🌙</button>
      <button class="refresh" onclick="loadAll()">새로고침</button>
    </div>
  </div>
  <nav>
    <a href="/admin/" class="active">🏠 홈</a>
    <a href="/availability/admin">📅 예약</a>
    <a href="/photos/admin">📸 사진</a>
  </nav>
</header>
<main>
  <div class="cards">
    <div class="stat clickable" onclick="openCard('total')">
      <div class="label">전체 문의</div><div class="value" id="s-total">-</div>
      <div class="sublabel">눌러서 전체 보기 ›</div>
    </div>
    <div class="stat accent clickable" onclick="openCard('today')">
      <div class="label">오늘 문의</div><div class="value" id="s-today">-</div>
      <div class="sublabel">눌러서 오늘 보기 ›</div>
    </div>
    <div class="stat green clickable" onclick="openCard('confirmed')">
      <div class="label">예약 확정 고객</div><div class="value" id="s-confirmed">-</div>
      <div class="sublabel" id="s-confirmed-sub">눌러서 명단 보기 ›</div>
    </div>
    <div class="stat warn clickable" onclick="openCard('revenue')">
      <div class="label">수입 (이번 달)</div><div class="value money" id="s-revenue">-</div>
      <div class="sublabel">눌러서 수입 보기 ›</div>
    </div>
    <div class="stat amber clickable" onclick="openCard('pending')">
      <div class="label">입금대기</div><div class="value" id="s-pending">-</div>
      <div class="sublabel" id="s-pending-sub">눌러서 대기 보기 ›</div>
    </div>
    <div class="stat danger clickable" onclick="openCard('noshow')">
      <div class="label">노쇼율 (이번 달)</div><div class="value" id="s-noshow">-</div>
      <div class="sublabel" id="s-noshow-sub">눌러서 노쇼 보기 ›</div>
    </div>
  </div>

  <h2>🔔 예약 의향 고객</h2>
  <div id="intents"><div class="empty">불러오는 중...</div></div>

  <h2>💬 최근 대화 기록</h2>
  <div id="convos"><div class="empty">불러오는 중...</div></div>
</main>

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
function applyTheme(t){
  if(t==='dark'){ document.documentElement.setAttribute('data-theme','dark'); document.getElementById('themebtn').textContent='☀️'; }
  else { document.documentElement.removeAttribute('data-theme'); document.getElementById('themebtn').textContent='🌙'; }
}
function toggleTheme(){
  const cur = document.documentElement.getAttribute('data-theme')==='dark'?'dark':'light';
  const next = cur==='dark'?'light':'dark';
  try{ localStorage.setItem('dash_theme', next); }catch(e){}
  applyTheme(next);
}
(function(){ let t='light'; try{ t=localStorage.getItem('dash_theme')||'light'; }catch(e){} applyTheme(t); })();

function fmt(ts){ if(!ts) return '-'; const d=new Date(ts); return d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function uid(s){ return s ? esc(String(s).slice(0,8))+'…' : '-'; }

function won(n){ return (Number(n)||0).toLocaleString('ko-KR')+'원'; }

async function loadAll(){
  try {
    const [stats,intents,convos,resStats,resList] = await Promise.all([
      fetch('api/stats').then(r=>r.json()),
      fetch('api/intents').then(r=>r.json()),
      fetch('api/conversations').then(r=>r.json()),
      fetch('api/reservation-stats').then(r=>r.json()),
      fetch('api/reservations').then(r=>r.json()),
    ]);
    window._convosAll = convos || [];
    window._resStats = resStats || {};
    window._resList = resList || [];

    document.getElementById('s-total').textContent = stats.total_conversations ?? 0;
    document.getElementById('s-today').textContent = stats.today_conversations ?? 0;
    document.getElementById('s-confirmed').textContent = (resStats.total_reservations ?? 0) + '건';
    document.getElementById('s-confirmed-sub').textContent =
      '누적 ' + (resStats.total_people ?? 0) + '명 · 눌러서 명단 ›';
    document.getElementById('s-revenue').textContent = won(resStats.month_revenue);
    document.getElementById('s-noshow').textContent = (resStats.month_noshow_rate ?? 0) + '%';
    document.getElementById('s-noshow-sub').textContent =
      '이번 달 ' + (resStats.month_noshow ?? 0) + '건 · 누적 ' + (resStats.noshow_total ?? 0) + '건 ›';
    document.getElementById('s-pending').textContent = (resStats.pending_total ?? 0) + '건';
    document.getElementById('s-pending-sub').textContent =
      (resStats.pending_people ?? 0) + '명 · ' + won(resStats.pending_amount) + ' 대기 ›';

    const it = document.getElementById('intents');
    it.innerHTML = intents.length ? intents.map(r=>{
      const memo = r.admin_memo || '';
      return `
      <div class="item" id="intent-${r.id}">
        <div class="head">
          <span class="tag">예약문의</span><span class="time">${fmt(r.created_at)}</span><span class="uid">${uid(r.user_id)}</span>
          <span class="spacer"></span>
          <button class="memobtn" onclick="editMemo(${r.id})">📝 메모</button>
          <span class="arrow clickable" style="cursor:pointer" onclick="openUser('${esc(r.user_id)}')">›</span>
        </div>
        <div class="q clickable" style="cursor:pointer" onclick="openUser('${esc(r.user_id)}')">${esc(r.user_message)}</div>
        <div class="memo-slot">${memo?`<div class="memo-view"><b>📝 메모:</b> ${esc(memo)}</div>`:''}</div>
      </div>`;
    }).join('')
      : '<div class="empty">아직 예약 의향 고객이 없습니다.</div>';
    window._intentMemo = {};
    intents.forEach(r=>window._intentMemo[r.id]=r.admin_memo||'');

    const cv = document.getElementById('convos');
    cv.innerHTML = convos.length ? convos.map(r=>`
      <div class="item clickable" onclick="openUser('${esc(r.user_id)}')">
        <div class="head"><span class="time">${fmt(r.created_at)}</span><span class="uid">${uid(r.user_id)}</span><span class="arrow">›</span></div>
        <div class="q">Q. ${esc(r.user_message)}</div>
        <div class="a">A. ${esc(r.bot_reply)}</div>
      </div>`).join('')
      : '<div class="empty">아직 대화 기록이 없습니다.</div>';
  } catch(e){
    console.error(e);
  }
}

let currentUserId = null;

async function openUser(userId){
  currentUserId = userId;
  const modal = document.getElementById('modal');
  document.getElementById('m-uid').textContent = 'ID: ' + userId;
  document.getElementById('m-body').innerHTML = '<div class="empty">불러오는 중...</div>';
  modal.classList.add('show');
  await renderUser();
}

async function renderUser(){
  try {
    const rows = await fetch('api/user?user_id=' + encodeURIComponent(currentUserId)).then(r=>r.json());
    const body = document.getElementById('m-body');
    if(!rows.length){ body.innerHTML = '<div class="empty">대화 기록이 없습니다.</div>'; return; }
    body.innerHTML = rows.map(r=>`
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
    window._convRows = {};
    rows.forEach(r=>window._convRows[r.id]=r);
  } catch(e){
    document.getElementById('m-body').innerHTML = '<div class="empty">불러오기 실패</div>';
  }
}

function editTurn(id){
  const r = window._convRows[id];
  const turn = document.getElementById('turn-'+id);
  if(!r || !turn) return;
  const view = turn.querySelector('.view');
  view.innerHTML = `
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
  const fd = new FormData();
  fd.append('id', id);
  fd.append('user_message', document.getElementById('ed-u-'+id).value);
  fd.append('bot_reply', document.getElementById('ed-b-'+id).value);
  await fetch('api/conversation/update', {method:'POST', body:fd});
  await renderUser();
  loadAll();
}

async function delTurn(id){
  if(!confirm('이 대화 1건을 삭제할까요?')) return;
  const fd = new FormData();
  fd.append('id', id);
  await fetch('api/conversation/delete', {method:'POST', body:fd});
  await renderUser();
  loadAll();
}

function closeUser(){ document.getElementById('modal').classList.remove('show'); }
function closeCard(){ document.getElementById('cardmodal').classList.remove('show'); }

/* ===== 통계 카드 상세보기 ===== */
function isToday(ts){
  if(!ts) return false;
  const opt = {timeZone:'Asia/Seoul'};
  return new Date(ts).toLocaleDateString('ko-KR',opt) === new Date().toLocaleDateString('ko-KR',opt);
}
function convListHTML(rows){
  if(!rows.length) return '<div class="empty">대화가 없습니다.</div>';
  return rows.map(r=>`
    <div class="item clickable" onclick="closeCard();openUser('${esc(r.user_id)}')">
      <div class="head"><span class="time">${fmt(r.created_at)}</span><span class="uid">${uid(r.user_id)}</span><span class="arrow">›</span></div>
      <div class="q">Q. ${esc(r.user_message)}</div>
      <div class="a">A. ${esc(r.bot_reply)}</div>
    </div>`).join('');
}
function resRowHTML(r){
  const d = (r.slot_date||'').slice(5);
  const meta = [r.platform, r.memo].filter(Boolean).map(esc).join(' · ');
  const amt = Number(r.amount)||0;
  return `<div class="resrow">
    <div class="d"><div class="dd">${esc(d)||'-'}</div><div class="tt">${esc(r.time_slot)||''}</div></div>
    <div class="c"><div class="nm">${esc(r.customer_name)||'(이름없음)'} · ${esc(r.program)}</div>${meta?`<div class="mt">${meta}</div>`:''}</div>
    <div class="r"><div class="pp">${r.people}명</div>${amt>0?`<div class="am">${won(amt)}</div>`:''}</div>
  </div>`;
}
function openCard(type){
  const title = document.getElementById('cm-title');
  const body = document.getElementById('cm-body');
  const convos = window._convosAll || [];
  const rs = window._resStats || {};
  const list = window._resList || [];
  if(type==='total'){
    title.textContent = '💬 전체 문의 ('+convos.length+'건)';
    body.innerHTML = convListHTML(convos);
  } else if(type==='today'){
    const t = convos.filter(r=>isToday(r.created_at));
    title.textContent = '📅 오늘 문의 ('+t.length+'건)';
    body.innerHTML = convListHTML(t);
  } else if(type==='confirmed'){
    title.textContent = '✅ 예약 확정 고객';
    body.innerHTML = `
      <div class="revbox">
        <div class="b"><div class="k">오늘 예약</div><div class="v">${rs.today_reservations||0}건</div></div>
        <div class="b"><div class="k">이번 달</div><div class="v">${rs.month_reservations||0}건</div></div>
        <div class="b"><div class="k">누적 인원</div><div class="v">${rs.total_people||0}명</div></div>
      </div>` + (() => { const c = list.filter(r=>(r.status||'예약')==='예약'); return c.length ? c.map(resRowHTML).join('') : '<div class="empty">확정된 예약이 없습니다.</div>'; })();
  } else if(type==='revenue'){
    title.textContent = '💰 수입 관리';
    body.innerHTML = `
      <div class="revbox">
        <div class="b"><div class="k">오늘</div><div class="v">${won(rs.today_revenue)}</div></div>
        <div class="b hi"><div class="k">이번 달</div><div class="v">${won(rs.month_revenue)}</div></div>
        <div class="b"><div class="k">전체 누적</div><div class="v">${won(rs.total_revenue)}</div></div>
      </div>
      <div style="color:var(--sub);font-size:13px;margin-bottom:12px;">예약별 실수령 금액입니다(노쇼 제외). 금액 입력·수정은 📅 예약 화면에서 합니다.</div>
      ` + (() => { const c = list.filter(r=>(r.status||'예약')==='예약'); return c.length ? c.map(resRowHTML).join('') : '<div class="empty">확정 수입 건이 없습니다.</div>'; })();
  } else if(type==='pending'){
    const pd = list.filter(r=>(r.status||'예약')==='입금대기');
    title.textContent = '⏳ 입금대기 (가예약)';
    body.innerHTML = `
      <div class="revbox">
        <div class="b"><div class="k">대기 건수</div><div class="v">${rs.pending_total||0}건</div></div>
        <div class="b"><div class="k">대기 인원</div><div class="v">${rs.pending_people||0}명</div></div>
        <div class="b hi"><div class="k">대기 금액</div><div class="v">${won(rs.pending_amount)}</div></div>
      </div>
      <div style="color:var(--sub);font-size:13px;margin-bottom:12px;">자리는 잡아뒀지만 아직 입금 확인 전입니다. 입금 확인되면 📅 예약 화면에서 ✅를 눌러 확정하세요.</div>
      ` + (pd.length ? pd.map(resRowHTML).join('') : '<div class="empty">입금대기 건이 없습니다.</div>');
  } else if(type==='noshow'){
    const ns = list.filter(r=>(r.status||'예약')==='노쇼');
    title.textContent = '🚫 노쇼 내역';
    body.innerHTML = `
      <div class="revbox">
        <div class="b"><div class="k">이번 달 노쇼율</div><div class="v">${rs.month_noshow_rate||0}%</div></div>
        <div class="b hi"><div class="k">이번 달 노쇼</div><div class="v">${rs.month_noshow||0}건</div></div>
        <div class="b"><div class="k">누적 노쇼</div><div class="v">${rs.noshow_total||0}건</div></div>
      </div>
      <div style="color:var(--sub);font-size:13px;margin-bottom:12px;">노쇼는 잔여석에서 제외되지만 기록은 남습니다. 노쇼 표시·복원은 📅 예약 화면에서 합니다.</div>
      ` + (ns.length ? ns.map(resRowHTML).join('') : '<div class="empty">노쇼 기록이 없습니다. 👍</div>');
  }
  document.getElementById('cardmodal').classList.add('show');
}

document.addEventListener('keydown', e=>{ if(e.key==='Escape'){ closeUser(); closeCard(); } });

/* ===== 예약 의향 고객 메모 ===== */
function editMemo(id){
  const cur = (window._intentMemo && window._intentMemo[id]) || '';
  const slot = document.querySelector('#intent-'+id+' .memo-slot');
  if(!slot) return;
  slot.innerHTML = `
    <div class="memo-edit">
      <textarea id="memo-${id}" rows="2" placeholder="예: 6/7 데패강 4명 전화함 / 입금대기 / 노쇼주의">${esc(cur)}</textarea>
      <div class="bar">
        <button class="cancel" onclick="loadAll()">취소</button>
        <button class="ok" onclick="saveMemo(${id})">메모 저장</button>
      </div>
    </div>`;
  document.getElementById('memo-'+id).focus();
}

async function saveMemo(id){
  const fd = new FormData();
  fd.append('id', id);
  fd.append('memo', document.getElementById('memo-'+id).value);
  await fetch('api/conversation/memo', {method:'POST', body:fd});
  loadAll();
}

loadAll();
setInterval(loadAll, 30000);
</script>
</body>
</html>"""
