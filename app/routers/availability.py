"""예약 관리 (건별 입력 → 인원 자동 합산).

- GET  /availability/admin              → 관리 대시보드 HTML
- GET  /availability/api/config         → 종목/시간대/정원/플랫폼 구성
- GET  /availability/api/day?date=      → 해당 날짜 예약 건 + 슬롯 잔여 요약
- POST /availability/api/reservations   → 예약 건 추가
- POST /availability/api/reservations/delete → 예약 건 삭제
"""
import logging
import re
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routers.admin import require_admin
from app.services.auth import verify_session
from app.services import availability as av

PAY_OPTS = av.PAYMENT_METHODS

logger = logging.getLogger(__name__)
router = APIRouter()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(date: str) -> str:
    if not _DATE_RE.match(date):
        raise HTTPException(400, "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")
    return date


@router.get("/api/config")
async def get_config(_=Depends(require_admin)):
    return {"programs": av.PROGRAMS, "platforms": av.PLATFORMS, "today": av.today_str()}


@router.get("/api/day")
async def get_day(date: str, _=Depends(require_admin)):
    _check_date(date)
    reservations = await av.get_reservations(date)
    summary = await av.get_day_summary(date)
    return {"date": date, "reservations": reservations, "summary": summary}


@router.post("/api/reservations")
async def post_reservation(
    date: str = Form(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    program: str = Form(...),
    time_slot: str = Form(""),
    customer_name: str = Form(""),
    people: int = Form(1),
    platform: str = Form("현장"),
    memo: str = Form(""),
    amount: str = Form("0"),
    payment_method: str = Form("계좌이체"),
    deposit_amount: str = Form("0"),
    _=Depends(require_admin),
):
    row = await av.add_reservation(
        date, program, time_slot, customer_name, people, platform, memo, amount, payment_method, deposit_amount
    )
    return {"ok": True, "reservation": row}


@router.post("/api/reservations/update")
async def update_reservation(
    id: int = Form(...),
    date: str = Form(""),
    program: str = Form(...),
    time_slot: str = Form(""),
    customer_name: str = Form(""),
    people: int = Form(1),
    platform: str = Form("현장"),
    memo: str = Form(""),
    amount: str = Form("0"),
    payment_method: str = Form("계좌이체"),
    deposit_amount: str = Form("0"),
    _=Depends(require_admin),
):
    row = await av.update_reservation(
        id, program, time_slot, customer_name, people, platform, memo, amount, payment_method, deposit_amount, date
    )
    return {"ok": True, "reservation": row}


@router.post("/api/reservations/delete")
async def delete_reservation(
    id: int = Form(...),
    _=Depends(require_admin),
):
    await av.delete_reservation(id)
    return {"ok": True}


@router.post("/api/reservations/status")
async def set_status(
    id: int = Form(...),
    status: str = Form("예약"),
    _=Depends(require_admin),
):
    row = await av.set_reservation_status(id, status)
    return {"ok": True, "reservation": row}


@router.get("/admin", response_class=HTMLResponse)
async def availability_admin(asess: str | None = Cookie(default=None)):
    if not verify_session(asess):
        return RedirectResponse(url="/admin/login", status_code=302)
    return HTMLResponse(ADMIN_HTML)


ADMIN_HTML = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#09090d" media="(prefers-color-scheme: dark)">
<link rel="manifest" href="/static/manifest.json">
<link rel="apple-touch-icon" href="/static/icon-192.png">
<title>예약 관리</title>
<style>
  :root {
    --bg:#f6f8fa; --card:#ffffff; --line:#d0d7de; --txt:#1f2328; --sub:#57606a;
    --ok:#1a7f4f; --ok-bg:#dafbe1; --full:#d1242f; --full-bg:#ffebe9;
    --warn:#9a6700; --warn-bg:#fff8c5; --accent:#6366f1; --accent-press:#4f46e5;
    --field:#f6f8fa; --shadow:0 1px 3px rgba(0,0,0,.08);
    --header-bg:rgba(255,255,255,.92);
  }
  [data-theme="dark"] {
    --bg:#09090d; --card:#111116; --line:#1e2028; --txt:#e4e7ef; --sub:#6b7280;
    --ok:#34d399; --ok-bg:#06190e; --full:#f87171; --full-bg:#1a0606;
    --warn:#fbbf24; --warn-bg:#1c1500; --accent:#818cf8; --accent-press:#6366f1;
    --field:#0d0f14; --shadow:none;
    --header-bg:rgba(9,9,13,.85);
  }
  * { box-sizing:border-box; }
  html { -webkit-text-size-adjust:100%; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
         background:var(--bg); color:var(--txt); font-size:17px; line-height:1.45; }
  header { background:var(--header-bg); backdrop-filter:saturate(180%) blur(12px);
           -webkit-backdrop-filter:saturate(180%) blur(12px);
           border-bottom:1px solid var(--line); position:sticky; top:0; z-index:10; }
  .htop { padding:14px 18px; display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .brand { font-size:19px; font-weight:800; }
  .brand span { color:var(--sub); font-weight:600; font-size:14px; margin-left:4px; }
  .htools { display:flex; align-items:center; gap:6px; }
  .themebtn { background:var(--field); border:1px solid var(--line); color:var(--txt);
              width:40px; height:40px; border-radius:10px; cursor:pointer; font-size:19px; padding:0;
              display:flex; align-items:center; justify-content:center; }
  .logoutbtn { color:var(--sub); font-size:13px; font-weight:600; text-decoration:none;
               padding:9px 12px; border-radius:10px; background:var(--field);
               border:1px solid var(--line); white-space:nowrap; }
  .logoutbtn:hover { color:var(--txt); }
  nav { display:flex; gap:6px; padding:0 12px 12px; overflow-x:auto; }
  nav a { flex:1; text-align:center; white-space:nowrap; text-decoration:none; color:var(--sub);
          font-size:16px; font-weight:700; padding:11px 10px; border-radius:10px; background:var(--field); border:1px solid var(--line); }
  nav a.active { color:#fff; background:var(--accent); border-color:var(--accent); }
  main { padding:18px; max-width:820px; margin:0 auto; }

  .datebar { display:flex; gap:8px; align-items:center; margin-bottom:18px; flex-wrap:wrap; }
  input[type=date] { background:var(--field); border:1px solid var(--line); color:var(--txt);
                     padding:12px 14px; border-radius:10px; font-size:17px; flex:1; min-width:150px; }
  .quick { background:var(--field); color:var(--txt); border:1px solid var(--line);
           padding:12px 16px; border-radius:10px; cursor:pointer; font-size:16px; font-weight:600; }
  .quick:active { background:var(--accent); color:#fff; }

  .card { background:var(--card); border:1px solid var(--line); border-radius:16px;
          padding:14px; margin-bottom:12px; box-shadow:var(--shadow); }
  .card h2 { font-size:15px; margin:0 0 10px; color:var(--sub); font-weight:700; }

  /* ===== 잔여 좌석: 컴팩트 카드 ===== */
  .seatlegend { display:flex; flex-wrap:wrap; gap:6px 14px; margin-bottom:8px; }
  .seatlegend .lg { display:flex; align-items:center; gap:5px; font-size:13px; color:var(--sub); font-weight:600; }
  .seatlegend .lg i { width:11px; height:11px; border-radius:3px; display:inline-block; }
  .sumgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(110px,1fr)); gap:8px; }
  .seat { position:relative; overflow:hidden; border:1.5px solid var(--line); border-radius:12px; padding:10px 12px 8px; background:var(--field); }
  .seat .gbar { height:4px; margin:-10px -12px 8px; background:var(--gc,#64748b); }
  .seat .stop { font-size:12px; color:var(--gc,var(--sub)); font-weight:800; margin-bottom:1px; }
  /* 종목별 색 (상단 띠 + 종목명) */
  .seat.grp-paddle { --gc:#2563eb; }
  .seat.grp-kayak  { --gc:#7c3aed; }
  .seat.grp-wind   { --gc:#0d9488; }
  .seat.grp-foil   { --gc:#db2777; }
  .seat.grp-etc    { --gc:#64748b; }
  .seat .stime { font-size:13px; font-weight:700; margin-bottom:4px; }
  .seat .big { font-size:24px; font-weight:900; line-height:1; }
  .seat .frac { font-size:12px; color:var(--sub); margin-top:3px; font-weight:600; }
  .seat.ok   { border-color:var(--ok);   background:var(--ok-bg); }
  .seat.warn { border-color:var(--warn); background:var(--warn-bg); }
  .seat.full { border-color:var(--full); background:var(--full-bg); }
  .seat.ok .big   { color:var(--ok); }
  .seat.warn .big { color:var(--warn); }
  .seat.full .big { color:var(--full); }
  .seat.seatclick { cursor:pointer; transition:transform .1s; }
  .seat.seatclick:active { transform:scale(.97); }

  /* ===== 추가 폼 ===== */
  .form { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .form .field { display:flex; flex-direction:column; }
  .form label { font-size:13px; color:var(--sub); font-weight:600; margin-bottom:4px; }
  .form select, .form input { width:100%; background:var(--field); border:1px solid var(--line);
       color:var(--txt); padding:10px 12px; border-radius:10px; font-size:15px; }
  .form .full { grid-column:1 / -1; }
  .addbtn { grid-column:1 / -1; background:var(--accent); color:#fff; border:none;
            padding:13px; border-radius:12px; font-size:16px; font-weight:800; cursor:pointer; margin-top:2px; }
  .addbtn:active { background:var(--accent-press); }

  /* ===== 예약 목록 ===== */
  .pdot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:5px; vertical-align:middle; }
  .res-hdr { display:flex; align-items:center; padding:6px 4px 10px;
             border-bottom:2px solid var(--line); font-size:13px; font-weight:700; color:var(--sub); }
  .h-time { min-width:58px; }
  .h-prog { width:130px; }
  .h-name { flex:1; }
  .h-amt  { width:100px; text-align:right; }
  .h-acts { width:118px; }
  .res-row { border-bottom:1px solid var(--line); }
  .res-row:last-child { border-bottom:none; }
  .res-row:hover { background:var(--field); }
  .res-main { display:flex; align-items:center; gap:10px; padding:10px 4px; }
  .tr-noshow { opacity:.5; }
  .tr-noshow .r-nm { text-decoration:line-through; }
  .tr-pending  { border-left:3px solid #f59e0b; padding-left:6px; background:rgba(245,158,11,.06); }
  .tr-deposited { border-left:3px solid #10b981; padding-left:6px; background:rgba(16,185,129,.06); }
  .r-time { min-width:52px; font-weight:900; font-size:17px; color:var(--accent); white-space:nowrap; flex-shrink:0; }
  .r-prog { width:130px; font-size:14px; color:var(--sub); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex-shrink:0; }
  .r-body { flex:1; min-width:0; }
  .r-nm   { font-weight:700; font-size:16px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .r-meta { font-size:12px; color:var(--sub); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .r-sub  { display:none; font-size:12px; color:var(--sub); margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .r-amt  { width:90px; text-align:right; flex-shrink:0; }
  .r-amt .main-amt { font-weight:700; color:var(--ok); font-size:15px; white-space:nowrap; }
  .r-amt .dep-amt  { font-size:12px; color:#10b981; font-weight:600; margin-top:2px; }
  .r-acts { flex-shrink:0; white-space:nowrap; text-align:right; }
  .r-acts button { background:none; border:none; cursor:pointer; font-size:20px; padding:4px 3px; color:var(--sub); }
  .r-acts button:active { transform:scale(1.2); }
  .nobadge  { display:inline-block; font-size:11px; font-weight:800; color:#fff; background:var(--full);
              padding:1px 6px; border-radius:5px; margin-left:5px; vertical-align:middle; }
  .pendbadge { display:inline-block; font-size:11px; font-weight:800; color:#fff; background:#f59e0b;
               padding:1px 6px; border-radius:5px; margin-left:5px; vertical-align:middle; }
  .daysum { text-align:right; padding:14px 6px 2px; font-size:16px; color:var(--sub); }
  .daysum b { color:var(--ok); font-size:19px; font-weight:900; margin-left:6px; }
  .daysum small { color:var(--sub); font-weight:600; font-size:13px; }
  .empty { color:var(--sub); font-size:16px; padding:12px 0; text-align:center; }
  .hint { color:var(--sub); font-size:14px; margin-top:14px; line-height:1.6; }

  /* ===== 수정 모달 ===== */
  .modal-bg { position:fixed; inset:0; background:rgba(0,0,0,.5); display:none;
              align-items:flex-end; justify-content:center; z-index:100; }
  .modal-bg.show { display:flex; }
  .modal { background:var(--card); width:100%; max-width:560px; max-height:90vh;
           border-radius:18px 18px 0 0; display:flex; flex-direction:column; overflow:hidden; }
  .modal-head { padding:16px 20px; border-bottom:1px solid var(--line); display:flex;
                align-items:center; justify-content:space-between; }
  .modal-head .t { font-size:18px; font-weight:800; }
  .modal-head .x { background:var(--field); border:1px solid var(--line); color:var(--txt);
                   width:40px; height:40px; border-radius:10px; font-size:20px; cursor:pointer; }
  .modal-body { padding:18px 20px; overflow-y:auto; }
  .savebtn { width:100%; background:var(--accent); color:#fff; border:none; padding:16px;
             border-radius:12px; font-size:18px; font-weight:800; cursor:pointer; margin-top:6px; }
  .savebtn:active { background:var(--accent-press); }
  .delbtn-modal { width:100%; background:none; border:1.5px solid var(--full); color:var(--full);
                  padding:14px; border-radius:12px; font-size:16px; font-weight:700; cursor:pointer; margin-top:8px; }
  .delbtn-modal:active { background:var(--full); color:#fff; }

  /* ===== 모바일 ===== */
  @media (max-width:600px){
    body { font-size:16px; }
    main { padding:12px; padding-bottom: max(20px, env(safe-area-inset-bottom)); }

    /* 잔여석: 가로 스크롤 1줄 */
    .sumgrid { display:flex; overflow-x:auto; gap:8px; padding-bottom:4px;
               -webkit-overflow-scrolling:touch; grid-template-columns:unset; }
    .seat { min-width:96px; flex-shrink:0; }

    /* 폼: 2열 유지, 더 컴팩트 */
    .form { grid-template-columns:1fr 1fr; gap:8px; }
    .form label { font-size:12px; margin-bottom:3px; }
    .form select, .form input { padding:9px 10px; font-size:14px; }
    .addbtn { padding:12px; font-size:15px; }

    /* 예약 목록 */
    .res-hdr { display:none; }
    .r-prog  { display:none; }
    .r-amt   { display:none; }
    .r-sub   { display:block; }
    .r-acts .del-btn { display:none; }
    .r-acts button { font-size:21px; padding:4px 3px; min-width:34px; min-height:38px; }
  }
  @media (min-width:560px){ .modal-bg { align-items:center; } .modal { border-radius:18px; } }
</style></head>
<body>
<header>
  <div class="htop">
    <div class="brand">🏄 서퍼스트<span>관리자</span></div>
    <div class="htools">
      <button class="themebtn" id="themebtn" onclick="toggleTheme()" title="화면 톤 전환">🌙</button>
      <a href="/admin/logout" class="logoutbtn">로그아웃</a>
    </div>
  </div>
  <nav>
    <a href="/admin/">🏠 홈</a>
    <a href="/availability/admin" class="active">📅 예약</a>
    <a href="/photos/admin">📸 사진</a>
  </nav>
</header>
<main>
  <div class="datebar">
    <button class="quick" onclick="shiftDay(-1)" style="font-size:20px;padding:10px 14px;">‹</button>
    <input type="date" id="date">
    <button class="quick" onclick="shiftDay(1)" style="font-size:20px;padding:10px 14px;">›</button>
    <button class="quick" onclick="setDay(0)">오늘</button>
    <button class="quick" onclick="setDay(1)">내일</button>
    <button class="quick" onclick="setDay(2)">모레</button>
  </div>

  <div class="card">
    <h2>잔여 좌석 (자동 합산)</h2>
    <div class="seatlegend">
      <span class="lg"><i style="background:#2563eb"></i>패들보드</span>
      <span class="lg"><i style="background:#7c3aed"></i>카약</span>
      <span class="lg"><i style="background:#0d9488"></i>윈드서핑</span>
      <span class="lg"><i style="background:#db2777"></i>포일류</span>
    </div>
    <div class="sumgrid" id="summary"></div>
  </div>

  <div class="card">
    <h2>＋ 예약 추가</h2>
    <div class="form">
      <div class="field">
        <label>종목</label>
        <select id="f_prog" onchange="onProgChange()"></select>
      </div>
      <div class="field">
        <label>시간</label>
        <select id="f_time"></select>
        <input id="f_time_txt" placeholder="예: 16:00" style="display:none;">
      </div>
      <div class="field">
        <label>이름</label>
        <input id="f_name" placeholder="예: 김진수">
      </div>
      <div class="field">
        <label>인원</label>
        <input id="f_people" type="number" min="1" value="2">
      </div>
      <div class="field">
        <label>플랫폼</label>
        <select id="f_plat"></select>
      </div>
      <div class="field">
        <label>결제수단</label>
        <select id="f_pay">
          <option value="계좌이체">💳 계좌이체</option>
          <option value="현장카드">💳 현장카드</option>
          <option value="현금">💵 현금</option>
        </select>
      </div>
      <div class="field">
        <label>예약금 (원)</label>
        <input id="f_deposit" type="number" min="0" step="1000" inputmode="numeric" placeholder="예: 20000">
      </div>
      <div class="field">
        <label>실수령 금액 (원) <span id="price-hint" style="color:var(--accent);font-weight:600;font-size:13px;margin-left:6px;"></span></label>
        <input id="f_amount" type="number" min="0" step="1000" inputmode="numeric" placeholder="예: 80000">
      </div>
      <div class="field full">
        <label>메모 (사장님 전용 · 손님에게 안 보임)</label>
        <input id="f_memo" placeholder="예: 미입금 / 단체 / 외국인">
      </div>
      <button class="addbtn" onclick="addRes()">예약 추가</button>
    </div>
    <div class="hint">건만 추가하면 위 잔여 좌석이 자동으로 합산·마감 처리됩니다.<br>이름·플랫폼·메모는 챗봇/손님에게 절대 안 나갑니다.</div>
  </div>

  <div class="card">
    <h2 id="listttl">예약 목록</h2>
    <div id="list"></div>
  </div>
</main>

<div class="modal-bg" id="editmodal" onclick="if(event.target===this)closeEdit()">
  <div class="modal">
    <div class="modal-head">
      <div class="t">✏️ 예약 수정</div>
      <button class="x" onclick="closeEdit()">✕</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="e_id">
      <div class="form">
        <div class="field full">
          <label>날짜</label>
          <input type="date" id="e_date">
        </div>
        <div class="field">
          <label>종목</label>
          <select id="e_prog" onchange="onEditProgChange()"></select>
        </div>
        <div class="field">
          <label>시간</label>
          <select id="e_time"></select>
          <input id="e_time_txt" placeholder="예: 16:00" style="display:none;">
        </div>
        <div class="field">
          <label>이름</label>
          <input id="e_name" placeholder="예: 김진수">
        </div>
        <div class="field">
          <label>인원</label>
          <input id="e_people" type="number" min="1" value="1">
        </div>
        <div class="field">
          <label>플랫폼</label>
          <select id="e_plat"></select>
        </div>
        <div class="field">
          <label>결제수단</label>
          <select id="e_pay">
            <option value="계좌이체">💳 계좌이체</option>
            <option value="현장카드">💳 현장카드</option>
            <option value="현금">💵 현금</option>
          </select>
        </div>
        <div class="field">
          <label>예약금 (원)</label>
          <input id="e_deposit" type="number" min="0" step="1000" inputmode="numeric" placeholder="예: 20000">
        </div>
        <div class="field">
          <label>실수령 금액 (원)</label>
          <input id="e_amount" type="number" min="0" step="1000" inputmode="numeric" placeholder="예: 80000">
        </div>
        <div class="field full">
          <label>메모 (사장님 전용)</label>
          <input id="e_memo" placeholder="예: 미입금 / 단체 / 외국인">
        </div>
        <button class="savebtn" onclick="saveEdit()">수정 저장</button>
        <button class="delbtn-modal" onclick="delFromEdit()">🗑 예약 삭제</button>
      </div>
    </div>
  </div>
</div>

<div class="modal-bg" id="seatmodal" onclick="if(event.target===this)closeSeat()">
  <div class="modal">
    <div class="modal-head">
      <div>
        <div class="t" id="seat-title">예약자 명단</div>
        <div id="seat-sub" style="color:var(--sub);font-size:14px;margin-top:3px;"></div>
      </div>
      <button class="x" onclick="closeSeat()">✕</button>
    </div>
    <div class="modal-body" id="seat-body"></div>
  </div>
</div>
<script>
let CONFIG = null;
const dateEl = document.getElementById('date');
const $ = id => document.getElementById(id);

const PRICE_MAP = {
  '데이패들보드': '렌탈 3만원 / 강습포함 5만원 (1인)',
  '선셋패들보드': '렌탈 3만원 / 강습포함 5만원 (1인)',
  '데이카약':     '1인 3만원',
  '선셋카약':     '1인 3만원',
  '윈드서핑':     '렌탈 8만원 / 강습포함 12만원 (1인)',
  '전동e포일':    '렌탈 8만원 / 강습포함 15만원 (1인)',
  'E포일':        '렌탈 8만원 / 강습포함 15만원 (1인)',
  '펌핑포일':     '렌탈 7만원 / 강습포함 10만원 (1인)',
};

/* ===== 테마 ===== */
function applyTheme(t){
  if(t==='dark'){ document.documentElement.setAttribute('data-theme','dark'); $('themebtn').textContent='☀️'; }
  else { document.documentElement.removeAttribute('data-theme'); $('themebtn').textContent='🌙'; }
}
function toggleTheme(){
  const cur = document.documentElement.getAttribute('data-theme')==='dark' ? 'dark':'light';
  const next = cur==='dark' ? 'light':'dark';
  try{ localStorage.setItem('dash_theme', next); }catch(e){}
  applyTheme(next);
}
(function(){ let t='light'; try{ t=localStorage.getItem('dash_theme')||'light'; }catch(e){} applyTheme(t); })();

function setDay(offset){
  const d = new Date();
  d.setDate(d.getDate()+offset);
  dateEl.value = localDate(d);
  loadDay();
}
function shiftDay(delta){
  const base = dateEl.value || localToday();
  const d = new Date(base + 'T00:00:00');
  d.setDate(d.getDate()+delta);
  dateEl.value = localDate(d);
  loadDay();
}
function localDate(d){
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
}
function localToday(){
  return localDate(new Date());
}

let ROWS = [];

async function init(){
  CONFIG = await fetch('api/config').then(r=>r.json());
  const progOpts = CONFIG.programs.map(p=>`<option value="${p.key}">${p.key}</option>`).join('');
  const platOpts = CONFIG.platforms.map(p=>`<option value="${p}">${p}</option>`).join('');
  $('f_prog').innerHTML = progOpts;  $('f_plat').innerHTML = platOpts;
  $('e_prog').innerHTML = progOpts;  $('e_plat').innerHTML = platOpts;
  onProgChange();
  dateEl.value = CONFIG.today;
  dateEl.onchange = loadDay;
  loadDay();
}

function progByKey(k){ return CONFIG.programs.find(p=>p.key===k); }

function onProgChange(){
  const p = progByKey($('f_prog').value);
  const sel = $('f_time'), txt = $('f_time_txt');
  if(p && p.slots && p.slots.length){
    sel.style.display=''; txt.style.display='none';
    sel.innerHTML = p.slots.map(s=>`<option value="${s}">${s}</option>`).join('');
  } else {
    sel.style.display='none'; txt.style.display='';
    txt.value='';
  }
  const hint = $('price-hint');
  if(hint) hint.textContent = PRICE_MAP[$('f_prog').value] ? '· 단가 참고: ' + PRICE_MAP[$('f_prog').value] : '';
}

function getTime(){
  const p = progByKey($('f_prog').value);
  return (p && p.slots && p.slots.length) ? $('f_time').value : $('f_time_txt').value.trim();
}

function seatClass(s){
  if(s.is_full) return 'full';
  if(s.remaining <= Math.max(1, Math.floor(s.capacity*0.2))) return 'warn';
  return 'ok';
}

async function loadDay(){
  const date = dateEl.value;
  const data = await fetch('api/day?date='+date).then(r=>r.json());
  ROWS = data.reservations;
  renderSummary(data.summary);
  renderList(data.reservations);
}

function progGroup(name){
  name = name || '';
  if(name.indexOf('패들') >= 0) return 'paddle';
  if(name.indexOf('카약') >= 0) return 'kayak';
  if(name.indexOf('윈드') >= 0) return 'wind';
  if(name.indexOf('포일') >= 0) return 'foil';
  return 'etc';
}

function renderSummary(summary){
  window._summary = summary;
  const el = $('summary');
  if(!summary.length){ el.innerHTML = '<span class="empty">정원 관리 종목 없음</span>'; return; }
  el.innerHTML = summary.map((s,i)=>{
    const big = s.is_full ? '마감' : s.remaining+'<small style="font-size:16px;">자리</small>';
    const cls = s.booked>0 ? 'seatclick' : '';
    return `<div class="seat ${seatClass(s)} grp-${progGroup(s.program)} ${cls}" onclick="openSeat(${i})">
      <div class="gbar"></div>
      <div class="stop">${esc(s.program)}</div>
      <div class="stime">${esc(s.time_slot)}</div>
      <div class="big">${big}</div>
      <div class="frac">${s.booked}/${s.capacity}명${s.booked>0?' ›':''}</div>
    </div>`;
  }).join('');
}

function esc(t){ return (t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

const PROG_COLOR = {
  '패들': '#2563eb', '카약': '#7c3aed', '윈드': '#0d9488', '포일': '#db2777'
};
function progColor(name){
  name = name||'';
  if(name.includes('패들')) return '#2563eb';
  if(name.includes('카약')) return '#7c3aed';
  if(name.includes('윈드')) return '#0d9488';
  if(name.includes('포일')) return '#db2777';
  return '#64748b';
}

function renderList(rows){
  $('listttl').textContent = `예약 목록 (${rows.length}건)`;
  const el = $('list');
  if(!rows.length){ el.innerHTML = '<div class="empty">이 날짜에 입력된 예약이 없습니다.</div>'; return; }
  let sumAmt = 0;
  const hdr = `<div class="res-hdr"><span class="h-time">시간</span><span class="h-prog">종목</span><span class="h-name">이름</span><span class="h-amt">금액</span><span class="h-acts"></span></div>`;
  const rowsHtml = rows.map(r=>{
    const meta = [r.platform, r.payment_method, r.memo].filter(Boolean).map(esc).join(' · ');
    const st = (r.status||'예약');
    const isNo = st==='노쇼';
    const isPend = st==='입금대기';
    const amt = Number(r.amount)||0; if(st==='예약') sumAmt += amt;
    const dep = Number(r.deposit_amount)||0;
    const hasDeposit = dep > 0;
    const rowCls = isNo ? 'tr-noshow' : (isPend ? 'tr-pending' : (hasDeposit ? 'tr-deposited' : ''));
    let badge = '';
    if(isNo) badge = '<span class="nobadge">노쇼</span>';
    else if(isPend) badge = '<span class="pendbadge">입금대기</span>';
    let acts = '';
    if(isNo){
      acts = `<button onclick="setStatus(${r.id},'예약')" title="복원">↩️</button>`;
    } else if(isPend){
      acts = `<button onclick="setStatus(${r.id},'예약')" title="입금확인 → 확정">✅</button>`
           + `<button onclick="setStatus(${r.id},'노쇼')" title="노쇼">🚫</button>`;
    } else {
      acts = `<button onclick="setStatus(${r.id},'입금대기')" title="입금대기로 전환">⏳</button>`
           + `<button onclick="setStatus(${r.id},'노쇼')" title="노쇼">🚫</button>`;
    }
    const subParts = [r.program, r.people+'명', ...(amt?[amt.toLocaleString('ko-KR')+'원']:[]), ...(hasDeposit?['예약금 '+dep.toLocaleString('ko-KR')+'원']:[])];
    return `<div class="res-row ${rowCls}"><div class="res-main">
      <div class="r-time">${esc(r.time_slot)||'-'}</div>
      <div class="r-prog"><span class="pdot" style="background:${progColor(r.program)}"></span>${esc(r.program)}</div>
      <div class="r-body">
        <div class="r-nm">${esc(r.customer_name)||'(이름없음)'} ${badge}</div>
        ${meta?`<div class="r-meta">${meta}</div>`:''}
        <div class="r-sub"><span class="pdot" style="background:${progColor(r.program)}"></span>${subParts.map(esc).join(' · ')}</div>
      </div>
      <div class="r-amt">${amt>0?`<div class="main-amt">${amt.toLocaleString('ko-KR')}원</div>`:''}${hasDeposit?`<div class="dep-amt">예약금 ${dep.toLocaleString('ko-KR')}원</div>`:''}</div>
      <div class="r-acts">${acts}<button onclick="openEdit(${r.id})" title="수정">✏️</button><button class="del-btn" onclick="delRes(${r.id})" title="삭제">🗑</button></div>
    </div></div>`;
  }).join('');
  el.innerHTML = hdr + rowsHtml
    + (sumAmt>0?`<div class="daysum">이 날짜 확정 수입 <b>${sumAmt.toLocaleString('ko-KR')}원</b> <small>(입금대기·노쇼 제외)</small></div>`:'');
}

async function addRes(){
  const time = getTime();
  const fd = new FormData();
  fd.append('date', dateEl.value);
  fd.append('program', $('f_prog').value);
  fd.append('time_slot', time);
  fd.append('customer_name', $('f_name').value.trim());
  fd.append('people', $('f_people').value || '1');
  fd.append('platform', $('f_plat').value);
  fd.append('payment_method', $('f_pay').value);
  fd.append('deposit_amount', $('f_deposit').value || '0');
  fd.append('memo', $('f_memo').value.trim());
  fd.append('amount', $('f_amount').value || '0');
  const res = await fetch('api/reservations', {method:'POST', body:fd});
  if(!res.ok){
    const t = await res.text();
    alert('예약 추가 실패 ('+res.status+')\\n'+t.slice(0,500));
    return;
  }
  $('f_name').value=''; $('f_memo').value=''; $('f_people').value='2'; $('f_amount').value=''; $('f_deposit').value=''; $('f_pay').value='계좌이체';
  loadDay();
}

async function delRes(id){
  if(!confirm('이 예약을 삭제할까요?')) return;
  const fd = new FormData();
  fd.append('id', id);
  await fetch('api/reservations/delete', {method:'POST', body:fd});
  loadDay();
}

async function setStatus(id, status){
  let msg;
  if(status==='노쇼') msg = '노쇼로 표시할까요?\\n자리는 다시 풀리지만 기록은 남습니다.';
  else if(status==='입금대기') msg = '입금대기(가예약)로 전환할까요?\\n자리는 잡아두지만 입금 확인 전까지 수입엔 안 잡힙니다.';
  else msg = '입금확인 → 예약으로 확정할까요?';
  if(!confirm(msg)) return;
  const fd = new FormData();
  fd.append('id', id);
  fd.append('status', status);
  const res = await fetch('api/reservations/status', {method:'POST', body:fd});
  if(!res.ok){
    const t = await res.text();
    alert('상태 변경 실패 ('+res.status+')\\n'+t.slice(0,500));
    return;
  }
  loadDay();
}

/* ===== 수정 ===== */
function onEditProgChange(){
  const p = progByKey($('e_prog').value);
  const sel = $('e_time'), txt = $('e_time_txt');
  if(p && p.slots && p.slots.length){
    sel.style.display=''; txt.style.display='none';
    sel.innerHTML = p.slots.map(s=>`<option value="${s}">${s}</option>`).join('');
  } else {
    sel.style.display='none'; txt.style.display='';
  }
}

function openEdit(id){
  const r = ROWS.find(x=>x.id===id);
  if(!r) return;
  $('e_id').value = r.id;
  $('e_date').value = r.slot_date || dateEl.value;
  $('e_prog').value = r.program;
  onEditProgChange();
  const p = progByKey(r.program);
  if(p && p.slots && p.slots.length){ $('e_time').value = r.time_slot || p.slots[0]; }
  else { $('e_time_txt').value = r.time_slot || ''; }
  $('e_name').value = r.customer_name || '';
  $('e_people').value = r.people || 1;
  $('e_plat').value = r.platform || CONFIG.platforms[0];
  $('e_pay').value = r.payment_method || '계좌이체';
  $('e_deposit').value = (Number(r.deposit_amount)||0) ? r.deposit_amount : '';
  $('e_memo').value = r.memo || '';
  $('e_amount').value = (Number(r.amount)||0) ? r.amount : '';
  $('editmodal').classList.add('show');
}

function getEditTime(){
  const p = progByKey($('e_prog').value);
  return (p && p.slots && p.slots.length) ? $('e_time').value : $('e_time_txt').value.trim();
}

async function saveEdit(){
  const fd = new FormData();
  fd.append('id', $('e_id').value);
  fd.append('date', $('e_date').value);
  fd.append('program', $('e_prog').value);
  fd.append('time_slot', getEditTime());
  fd.append('customer_name', $('e_name').value.trim());
  fd.append('people', $('e_people').value || '1');
  fd.append('platform', $('e_plat').value);
  fd.append('payment_method', $('e_pay').value);
  fd.append('deposit_amount', $('e_deposit').value || '0');
  fd.append('memo', $('e_memo').value.trim());
  fd.append('amount', $('e_amount').value || '0');
  const res = await fetch('api/reservations/update', {method:'POST', body:fd});
  if(!res.ok){
    const t = await res.text();
    alert('예약 수정 실패 ('+res.status+')\\n'+t.slice(0,500));
    return;
  }
  closeEdit();
  loadDay();
}

async function delFromEdit(){
  const id = Number($('e_id').value);
  if(!id) return;
  if(!confirm('이 예약을 삭제할까요?')) return;
  const fd = new FormData();
  fd.append('id', id);
  await fetch('api/reservations/delete', {method:'POST', body:fd});
  closeEdit();
  loadDay();
}

function closeEdit(){ $('editmodal').classList.remove('show'); }

/* ===== 좌석 클릭 → 예약자 명단 ===== */
function openSeat(i){
  const s = (window._summary||[])[i];
  if(!s || !s.booked) return;
  const rows = ROWS.filter(r=>r.program===s.program && (r.time_slot||'')===(s.time_slot||''));
  $('seat-title').textContent = `${s.program} ${s.time_slot}`;
  $('seat-sub').textContent = `예약 ${s.booked}/${s.capacity}명 · 잔여 ${s.remaining}명 (이름을 누르면 수정)`;
  const body = $('seat-body');
  body.innerHTML = rows.length ? `<div class="tbl-wrap"><table class="restable">
    <thead><tr><th>이름</th><th>인원</th><th>금액</th><th></th></tr></thead>
    <tbody>${rows.map(r=>{
      const meta = [r.platform, r.payment_method, r.memo].filter(Boolean).map(esc).join(' · ');
      const amt = Number(r.amount)||0;
      const dep = Number(r.deposit_amount)||0;
      return `<tr onclick="closeSeat();openEdit(${r.id})" style="cursor:pointer">
        <td><div class="tc-nm">${esc(r.customer_name)||'(이름없음)'}</div>${meta?`<div class="tc-meta">${meta}</div>`:''}</td>
        <td class="tc-ppl">${r.people}<small style="font-size:12px;color:var(--sub)">명</small></td>
        <td class="tc-amt">${amt>0?`<div class="main-amt">${amt.toLocaleString('ko-KR')}원</div>`:''}${dep>0?`<div class="dep-amt">예약금 ${dep.toLocaleString('ko-KR')}원</div>`:''}</td>
        <td class="tc-acts"><button style="background:none;border:none;font-size:18px">✏️</button></td>
      </tr>`;
    }).join('')}</tbody>
  </table></div>` : '<div class="empty">이 시간대 예약이 없습니다.</div>';
  $('seatmodal').classList.add('show');
}
function closeSeat(){ $('seatmodal').classList.remove('show'); }

document.addEventListener('keydown', e=>{ if(e.key==='Escape'){ closeEdit(); closeSeat(); } });

init();
</script>
<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js');</script>
</body></html>"""