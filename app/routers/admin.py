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
from app.services.db import (
    get_recent_conversations,
    get_booking_intents,
    get_stats,
)

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


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard(_=Depends(require_admin)):
    return HTMLResponse(DASHBOARD_HTML)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>사장님 대시보드</title>
<style>
  :root { --bg:#0f1419; --card:#1a2129; --line:#2a3441; --txt:#e6edf3; --sub:#8b98a5; --accent:#3fb950; --warn:#f0883e; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif; background:var(--bg); color:var(--txt); }
  header { padding:20px 24px; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; }
  header h1 { font-size:18px; margin:0; }
  header .sub { color:var(--sub); font-size:13px; }
  main { padding:24px; max-width:1000px; margin:0 auto; }
  .cards { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-bottom:28px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px; }
  .card .label { color:var(--sub); font-size:13px; margin-bottom:8px; }
  .card .value { font-size:30px; font-weight:700; }
  .card.accent .value { color:var(--accent); }
  .card.warn .value { color:var(--warn); }
  h2 { font-size:15px; margin:24px 0 12px; }
  table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; }
  th,td { text-align:left; padding:11px 14px; font-size:13px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--sub); font-weight:600; background:#141b22; }
  tr:last-child td { border-bottom:none; }
  .tag { display:inline-block; background:var(--warn); color:#1a1006; font-size:11px; font-weight:700; padding:2px 7px; border-radius:6px; }
  .time { color:var(--sub); white-space:nowrap; }
  .uid { color:var(--sub); font-family:monospace; font-size:12px; }
  .empty { color:var(--sub); padding:24px; text-align:center; }
  .refresh { background:var(--accent); color:#04260c; border:none; padding:8px 14px; border-radius:8px; font-weight:700; cursor:pointer; font-size:13px; }
  .msg { max-width:380px; }
</style>
</head>
<body>
<header>
  <div><h1>사장님 대시보드</h1><div class="sub" id="shopname">WaterSports AI Agent</div></div>
  <button class="refresh" onclick="loadAll()">새로고침</button>
</header>
<main>
  <div class="cards">
    <div class="card"><div class="label">전체 문의</div><div class="value" id="s-total">-</div></div>
    <div class="card accent"><div class="label">오늘 문의</div><div class="value" id="s-today">-</div></div>
    <div class="card warn"><div class="label">예약 의향 고객</div><div class="value" id="s-intent">-</div></div>
  </div>

  <h2>🔔 예약 의향 고객</h2>
  <table>
    <thead><tr><th class="time">시간</th><th>고객</th><th>문의 내용</th></tr></thead>
    <tbody id="intents"><tr><td colspan="3" class="empty">불러오는 중...</td></tr></tbody>
  </table>

  <h2>💬 최근 대화 기록</h2>
  <table>
    <thead><tr><th class="time">시간</th><th>고객</th><th>고객 메시지 / AI 응답</th></tr></thead>
    <tbody id="convos"><tr><td colspan="3" class="empty">불러오는 중...</td></tr></tbody>
  </table>
</main>

<script>
function fmt(ts){ if(!ts) return '-'; const d=new Date(ts); return d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function uid(s){ return s ? esc(String(s).slice(0,8))+'…' : '-'; }

async function loadAll(){
  try {
    const [stats,intents,convos] = await Promise.all([
      fetch('api/stats').then(r=>r.json()),
      fetch('api/intents').then(r=>r.json()),
      fetch('api/conversations').then(r=>r.json()),
    ]);
    document.getElementById('s-total').textContent = stats.total_conversations ?? 0;
    document.getElementById('s-today').textContent = stats.today_conversations ?? 0;
    document.getElementById('s-intent').textContent = stats.booking_intents ?? 0;

    const it = document.getElementById('intents');
    it.innerHTML = intents.length ? intents.map(r=>`
      <tr><td class="time">${fmt(r.created_at)}</td><td class="uid">${uid(r.user_id)}</td>
      <td class="msg"><span class="tag">예약문의</span> ${esc(r.user_message)}</td></tr>`).join('')
      : '<tr><td colspan="3" class="empty">아직 예약 의향 고객이 없습니다.</td></tr>';

    const cv = document.getElementById('convos');
    cv.innerHTML = convos.length ? convos.map(r=>`
      <tr><td class="time">${fmt(r.created_at)}</td><td class="uid">${uid(r.user_id)}</td>
      <td class="msg"><b>Q.</b> ${esc(r.user_message)}<br><span style="color:#8b98a5"><b>A.</b> ${esc(r.bot_reply)}</span></td></tr>`).join('')
      : '<tr><td colspan="3" class="empty">아직 대화 기록이 없습니다.</td></tr>';
  } catch(e){
    console.error(e);
  }
}
loadAll();
setInterval(loadAll, 30000);
</script>
</body>
</html>"""