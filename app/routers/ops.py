"""개발자 전용 시스템 모니터링 (/ops/)."""
import hmac
import hashlib
import logging
import secrets
import time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Cookie, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

OPS_COOKIE = "opsess"
_SALT = b"surffirst_ops_2026"
KST = timezone(timedelta(hours=9))


def _make_token(pw: str) -> str:
    return hmac.new(pw.encode(), _SALT, hashlib.sha256).hexdigest()


def _verify(token: str | None) -> bool:
    pw = getattr(settings, "ops_password", "") or ""
    if not pw:
        return True
    if not token:
        return False
    return hmac.compare_digest(token, _make_token(pw))


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(opsess: str | None = Cookie(default=None)):
    if _verify(opsess):
        return RedirectResponse(url="/ops/", status_code=302)
    return HTMLResponse(_LOGIN_HTML.replace("{ERROR}", ""))


@router.post("/login")
async def login_submit(
    password: str = Form(...),
    remember: str = Form(default=""),
):
    pw = getattr(settings, "ops_password", "") or ""
    ok = not pw or secrets.compare_digest(password, pw)
    if not ok:
        return HTMLResponse(
            _LOGIN_HTML.replace("{ERROR}", '<div class="error">비밀번호가 올바르지 않습니다.</div>'),
            status_code=401,
        )
    token = _make_token(pw) if pw else ""
    resp = RedirectResponse(url="/ops/", status_code=302)
    max_age = 90 * 24 * 3600 if remember == "1" else None
    resp.set_cookie(OPS_COOKIE, token, max_age=max_age, httponly=True, samesite="lax")
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/ops/login", status_code=302)
    resp.delete_cookie(OPS_COOKIE)
    return resp


# ── API ───────────────────────────────────────────────────────────────────────

@router.get("/api/status")
async def api_status(opsess: str | None = Cookie(default=None)):
    if not _verify(opsess):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    now_kst = datetime.now(KST)

    # 날씨 캐시
    from app.services.agent import _cache as agent_cache
    w_ts, w_val = agent_cache.get("weather", (0, ""))
    a_ts, a_val = agent_cache.get("avail", (0, ""))
    w_age = int(time.monotonic() - w_ts) if w_ts else None
    a_age = int(time.monotonic() - a_ts) if a_ts else None

    # 네이버 동기화
    from app.services.naver import _processed, _token_cache, _last_ip_alert
    tok_exp = _token_cache.get("exp", 0)
    tok_ok = time.monotonic() < tok_exp - 60 if tok_exp else False

    # 대화 통계
    try:
        from app.services.db import get_supabase
        client = await get_supabase()
        total_r = await client.table("conversations").select("id", count="exact").execute()
        today_start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        today_r = await client.table("conversations").select("id", count="exact").gte("created_at", today_start.isoformat()).execute()
        intent_r = await client.table("conversations").select("id", count="exact").eq("is_booking_intent", True).execute()
        total_conv = total_r.count or 0
        today_conv = today_r.count or 0
        intent_conv = intent_r.count or 0
        db_ok = True
    except Exception as e:
        total_conv = today_conv = intent_conv = 0
        db_ok = False
        logger.warning(f"ops db 조회 실패: {e}")

    # 예약 통계
    try:
        from app.services.availability import get_reservation_stats
        res_stats = await get_reservation_stats()
        res_ok = True
    except Exception as e:
        res_stats = {}
        res_ok = False
        logger.warning(f"ops 예약 통계 실패: {e}")

    return {
        "server_time": now_kst.strftime("%Y-%m-%d %H:%M:%S KST"),
        "db_ok": db_ok,
        "res_ok": res_ok,
        "cache": {
            "weather_age_sec": w_age,
            "weather_val": w_val,
            "avail_age_sec": a_age,
            "avail_preview": (a_val or "")[:120],
        },
        "naver": {
            "token_valid": tok_ok,
            "processed_count": len(_processed),
            "last_ip_alert": int(_last_ip_alert) if _last_ip_alert else None,
        },
        "conversations": {
            "total": total_conv,
            "today": today_conv,
            "booking_intent": intent_conv,
        },
        "reservations": {
            "confirmed": res_stats.get("total_reservations", 0),
            "month_revenue": res_stats.get("month_revenue", 0),
            "noshow_rate": res_stats.get("noshow_rate", 0),
            "pending": res_stats.get("pending_total", 0),
        },
    }


# ── Page ──────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def ops_page(opsess: str | None = Cookie(default=None)):
    if not _verify(opsess):
        return RedirectResponse(url="/ops/login", status_code=302)
    return HTMLResponse(_OPS_HTML)


# ── HTML ──────────────────────────────────────────────────────────────────────

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ops 로그인</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{min-height:100svh;background:#09090d;display:flex;align-items:center;justify-content:center;
     font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;padding:24px;}
.card{background:#111116;border:1px solid #1e2028;border-radius:22px;padding:40px 32px;
      width:100%;max-width:360px;box-shadow:0 24px 64px rgba(0,0,0,.6);}
.logo{text-align:center;margin-bottom:32px;}
.logo .ico{font-size:44px;margin-bottom:10px;}
.logo .t{font-size:22px;font-weight:800;color:#e4e7ef;}
.logo .s{color:#6b7280;font-size:13px;margin-top:4px;}
label{display:block;color:#6b7280;font-size:12px;font-weight:700;letter-spacing:.6px;
      text-transform:uppercase;margin-bottom:8px;}
input[type=password]{width:100%;background:#0d0f14;border:1.5px solid #1e2028;color:#e4e7ef;
  border-radius:12px;padding:14px 16px;font-size:16px;font-family:inherit;outline:none;
  transition:border-color .2s;}
input[type=password]:focus{border-color:#818cf8;}
.remember{display:flex;align-items:center;gap:10px;margin:14px 0 22px;
          color:#6b7280;font-size:14px;cursor:pointer;}
.remember input{width:18px;height:18px;accent-color:#818cf8;cursor:pointer;}
.btn{width:100%;background:#818cf8;color:#fff;border:none;border-radius:12px;
     padding:15px;font-size:16px;font-weight:700;cursor:pointer;}
.btn:hover{background:#6366f1;}
.error{background:rgba(248,113,113,.1);border:1px solid rgba(248,113,113,.25);color:#f87171;
       border-radius:10px;padding:12px 14px;font-size:14px;margin-bottom:16px;}
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <div class="ico">⚙️</div>
    <div class="t">Ops 모니터링</div>
    <div class="s">개발자 전용</div>
  </div>
  {ERROR}
  <form method="post" action="/ops/login">
    <label>비밀번호</label>
    <input type="password" name="password" autofocus autocomplete="current-password" placeholder="OPS_PASSWORD">
    <label class="remember">
      <input type="checkbox" name="remember" value="1"> 90일간 로그인 유지
    </label>
    <button type="submit" class="btn">접속</button>
  </form>
</div>
</body>
</html>"""


_OPS_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Ops · 서퍼스트</title>
<style>
:root{
  --bg:#09090d;--card:#111116;--line:#1e2028;--txt:#e4e7ef;--sub:#6b7280;
  --accent:#818cf8;--green:#34d399;--red:#f87171;--warn:#fbbf24;
  --field:#0d0f14;
}
*{box-sizing:border-box;margin:0;padding:0;}
html{-webkit-text-size-adjust:100%;}
body{background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;
     font-size:15px;line-height:1.5;}
header{background:rgba(9,9,13,.9);border-bottom:1px solid var(--line);
       padding:14px 18px;display:flex;align-items:center;justify-content:space-between;
       position:sticky;top:0;z-index:10;backdrop-filter:blur(10px);}
.brand{font-size:17px;font-weight:800;}
.brand span{color:var(--sub);font-size:13px;margin-left:6px;font-weight:600;}
.htools{display:flex;gap:8px;align-items:center;}
.rbtn{background:var(--field);border:1px solid var(--line);color:var(--txt);
      height:36px;border-radius:9px;font-size:13px;font-weight:700;padding:0 12px;cursor:pointer;}
.rbtn:active{background:var(--accent);color:#fff;border-color:var(--accent);}
.logbtn{color:var(--sub);font-size:13px;font-weight:600;text-decoration:none;
        padding:8px 12px;border-radius:9px;background:var(--field);border:1px solid var(--line);}
.logbtn:hover{color:var(--txt);}
main{padding:16px;max-width:900px;margin:0 auto;
     padding-bottom:max(20px,env(safe-area-inset-bottom));}
.ts{color:var(--sub);font-size:13px;margin-bottom:16px;}

/* STATUS BAR */
.statusbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px;}
.chip{display:flex;align-items:center;gap:6px;background:var(--card);border:1px solid var(--line);
      border-radius:10px;padding:8px 12px;font-size:13px;font-weight:700;}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;}
.dot.ok{background:var(--green);}
.dot.warn{background:var(--warn);}
.dot.err{background:var(--red);}

/* GRID */
.grid{display:grid;grid-template-columns:1fr;gap:12px;}
@media(min-width:600px){.grid{grid-template-columns:1fr 1fr;}}
@media(min-width:900px){.grid{grid-template-columns:1fr 1fr 1fr;}}
.box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;}
.box h2{font-size:12px;font-weight:700;color:var(--sub);letter-spacing:.5px;
         text-transform:uppercase;margin-bottom:14px;display:flex;align-items:center;gap:6px;}
.row{display:flex;justify-content:space-between;align-items:baseline;
     padding:7px 0;border-bottom:1px solid var(--line);font-size:14px;}
.row:last-child{border-bottom:none;}
.rk{color:var(--sub);}
.rv{font-weight:700;}
.rv.ok{color:var(--green);}
.rv.warn{color:var(--warn);}
.rv.err{color:var(--red);}
.rv.accent{color:var(--accent);}

/* CACHE PREVIEW */
.preview{margin-top:10px;background:var(--field);border:1px solid var(--line);border-radius:8px;
         padding:10px;font-size:12px;color:var(--sub);line-height:1.6;
         white-space:pre-wrap;word-break:break-word;max-height:120px;overflow-y:auto;}

/* SECTION TITLE */
.stitle{font-size:14px;font-weight:800;margin:24px 0 10px;color:var(--sub);}

/* LOADING */
.loading{color:var(--sub);text-align:center;padding:40px;}
</style>
</head>
<body>
<header>
  <div class="brand">⚙️ Ops<span>개발자 전용</span></div>
  <div class="htools">
    <button class="rbtn" onclick="load()">↻ 새로고침</button>
    <a href="/admin/" class="logbtn">← 관리자</a>
    <a href="/ops/logout" class="logbtn">로그아웃</a>
  </div>
</header>
<main>
  <div class="ts" id="ts">불러오는 중…</div>

  <!-- STATUS CHIPS -->
  <div class="statusbar" id="statusbar"></div>

  <!-- GRID -->
  <div id="grid" class="grid"><div class="loading">불러오는 중…</div></div>
</main>
<script>
function fmtAge(sec) {
  if (sec === null || sec === undefined) return '없음';
  if (sec < 60) return sec + '초 전';
  if (sec < 3600) return Math.floor(sec/60) + '분 전';
  return Math.floor(sec/3600) + '시간 전';
}
function won(n) { return (Number(n)||0).toLocaleString('ko-KR') + '원'; }
function cls(ok) { return ok ? 'ok' : 'err'; }

async function load() {
  document.getElementById('ts').textContent = '불러오는 중…';
  try {
    const r = await fetch('api/status');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    render(d);
  } catch(e) {
    document.getElementById('grid').innerHTML = '<div class="loading" style="color:#f87171">불러오기 실패: ' + e.message + '</div>';
  }
}

function render(d) {
  document.getElementById('ts').textContent = '기준 시각: ' + d.server_time;

  // STATUS CHIPS
  const c = d.cache || {};
  const n = d.naver || {};
  const wOk = c.weather_age_sec !== null && c.weather_age_sec < 3600;
  const aOk = c.avail_age_sec !== null && c.avail_age_sec < 120;
  document.getElementById('statusbar').innerHTML = [
    chip(d.db_ok, 'DB 연결'),
    chip(d.res_ok, '예약 DB'),
    chip(wOk, '날씨 캐시'),
    chip(aOk, '잔여석 캐시'),
    chip(n.token_valid, '네이버 토큰'),
  ].join('');

  // GRID
  const cv = d.conversations || {};
  const rs = d.reservations || {};
  document.getElementById('grid').innerHTML = `
    <div class="box">
      <h2>💬 챗봇 대화</h2>
      <div class="row"><span class="rk">오늘 문의</span><span class="rv accent">${cv.today}건</span></div>
      <div class="row"><span class="rk">전체 누적</span><span class="rv">${cv.total}건</span></div>
      <div class="row"><span class="rk">예약 의향</span><span class="rv">${cv.booking_intent}건</span></div>
    </div>

    <div class="box">
      <h2>📅 예약 현황</h2>
      <div class="row"><span class="rk">확정 예약</span><span class="rv ok">${rs.confirmed}건</span></div>
      <div class="row"><span class="rk">이번달 수입</span><span class="rv accent">${won(rs.month_revenue)}</span></div>
      <div class="row"><span class="rk">입금대기</span><span class="rv ${rs.pending>0?'warn':'ok'}">${rs.pending}건</span></div>
      <div class="row"><span class="rk">누적 노쇼율</span><span class="rv ${rs.noshow_rate>10?'err':rs.noshow_rate>5?'warn':'ok'}">${rs.noshow_rate}%</span></div>
    </div>

    <div class="box">
      <h2>🌤 날씨 캐시</h2>
      <div class="row"><span class="rk">갱신</span><span class="rv ${wOk?'ok':'warn'}">${fmtAge(c.weather_age_sec)}</span></div>
      <div class="row"><span class="rk">상태</span><span class="rv" style="font-size:12px;text-align:right;max-width:170px">${(c.weather_val||'없음').slice(0,30)}</span></div>
    </div>

    <div class="box">
      <h2>📊 잔여석 캐시</h2>
      <div class="row"><span class="rk">갱신</span><span class="rv ${aOk?'ok':'warn'}">${fmtAge(c.avail_age_sec)}</span></div>
      ${c.avail_preview ? `<div class="preview">${esc(c.avail_preview)}</div>` : '<div class="row"><span class="rk">데이터</span><span class="rv">없음</span></div>'}
    </div>

    <div class="box">
      <h2>🛒 네이버 동기화</h2>
      <div class="row"><span class="rk">API 토큰</span><span class="rv ${n.token_valid?'ok':'warn'}">${n.token_valid?'유효':'만료/미발급'}</span></div>
      <div class="row"><span class="rk">처리된 주문</span><span class="rv">${n.processed_count}건 (세션)</span></div>
      <div class="row"><span class="rk">IP 변경 알림</span><span class="rv ${n.last_ip_alert?'warn':'ok'}">${n.last_ip_alert?'발생한 적 있음':'없음'}</span></div>
    </div>

    <div class="box">
      <h2>🔗 바로가기</h2>
      <div class="row"><a href="/admin/" style="color:var(--accent);text-decoration:none;font-weight:700">🏠 관리자 홈</a></div>
      <div class="row"><a href="/availability/admin" style="color:var(--accent);text-decoration:none;font-weight:700">📅 예약 관리</a></div>
      <div class="row"><a href="/dashboard/" style="color:var(--accent);text-decoration:none;font-weight:700">📊 분석 대시보드</a></div>
      <div class="row"><a href="/health" style="color:var(--accent);text-decoration:none;font-weight:700">❤️ 헬스체크 API</a></div>
    </div>`;
}

function chip(ok, label) {
  return `<div class="chip"><span class="dot ${ok?'ok':'err'}"></span>${label}</div>`;
}
function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

load();
setInterval(load, 30000);
</script>
</body>
</html>"""
