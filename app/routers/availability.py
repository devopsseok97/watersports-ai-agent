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
    status: str = Form("예약"),
    _=Depends(require_admin),
):
    row = await av.add_reservation(
        date, program, time_slot, customer_name, people, platform, memo, amount, payment_method, deposit_amount,
        status=status,
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


CSS_VER = "20260826-seats"


@router.get("/admin", response_class=HTMLResponse)
async def availability_admin(asess: str | None = Cookie(default=None)):
    if not verify_session(asess):
        return RedirectResponse(url="/admin/login", status_code=302)
    return HTMLResponse(ADMIN_HTML.replace("{CSS_VER}", CSS_VER))


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
<link rel="stylesheet" href="/static/admin/surf-admin.css?v={CSS_VER}">
<title>서퍼스트 · 예약 관리</title>
<style>
  /* ===== 잔여석: 종목별 그룹 + 진행바 ===== */
  .seats-panel .panel-headline { align-items: flex-start; }
  .seats-summary {
    font-size: 13px; font-weight: 800; color: var(--sf-ink);
    display: flex; align-items: center; gap: 6px;
    flex-wrap: wrap; justify-content: flex-end;
  }
  .seats-summary small { color: var(--sf-muted); font-weight: 700; margin-left: 2px; }

  .seat-groups { display: grid; gap: 10px; }
  .seat-group {
    border: 1px solid var(--sf-line-soft);
    border-radius: var(--sf-radius);
    background: var(--sf-surface);
    overflow: hidden;
  }
  .seat-group.grp-paddle { --gc: var(--sf-blue); }
  .seat-group.grp-kayak  { --gc: var(--sf-purple); }
  .seat-group.grp-wind   { --gc: var(--sf-river); }
  .seat-group.grp-foil   { --gc: #db2777; }
  .seat-group.grp-etc    { --gc: var(--sf-muted); }
  .seat-group__head {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px;
    padding: 9px 12px;
    background: color-mix(in srgb, var(--gc) 8%, transparent);
    border-bottom: 1px solid var(--sf-line-soft);
    border-left: 3px solid var(--gc);
  }
  .seat-group__title {
    display: flex; align-items: center; gap: 8px;
    font-size: 14px; font-weight: 900; letter-spacing: -0.01em;
    min-width: 0;
  }
  .seat-group__title b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .seat-group__dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--gc);
    flex-shrink: 0;
  }
  .seat-group__meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .seat-group__count {
    font-size: 14px; font-weight: 900; color: var(--sf-ink);
    font-variant-numeric: tabular-nums;
  }
  .seat-group__count small {
    color: var(--sf-muted); font-weight: 700; font-size: 11px;
    margin-left: 2px;
  }

  .seat-group__slots { display: grid; }
  .seat-row {
    display: grid;
    grid-template-columns: 52px minmax(60px, 1fr) 72px;
    grid-template-rows: auto auto;
    grid-template-areas:
      "time bar num"
      "time meta meta";
    column-gap: 12px; row-gap: 2px;
    padding: 10px 12px;
    align-items: center;
    background: transparent;
    border: 0;
    border-top: 1px solid var(--sf-line-soft);
    text-align: left; color: inherit;
    cursor: default;
    width: 100%;
    min-height: var(--sf-tap);
  }
  .seat-row:first-child { border-top: 0; }
  .seat-row.clickable { cursor: pointer; }
  .seat-row.clickable:hover { background: color-mix(in srgb, var(--gc, var(--sf-river)) 5%, transparent); }

  .seat-row__time {
    grid-area: time;
    font-weight: 900; font-size: 14px; color: var(--sf-ink);
    font-variant-numeric: tabular-nums;
    align-self: center;
  }
  .seat-row__bar {
    grid-area: bar;
    height: 8px; border-radius: 999px;
    background: var(--sf-line-soft);
    overflow: hidden;
    align-self: center;
  }
  .seat-row__fill {
    display: block; height: 100%; border-radius: 999px;
    background: var(--gc, var(--sf-river));
    transition: width .25s ease;
  }
  .seat-row.warn .seat-row__fill { background: var(--sf-yellow); }
  .seat-row.full .seat-row__fill { background: var(--sf-red); }
  .seat-row__num {
    grid-area: num;
    text-align: right;
    font-weight: 900; font-size: 17px; color: var(--sf-ink);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
    align-self: center;
  }
  .seat-row__num small {
    font-size: 11px; color: var(--sf-muted);
    font-weight: 700; margin-left: 2px;
  }
  .seat-row__badge {
    display: inline-block;
    background: var(--sf-red-soft); color: var(--sf-red);
    font-size: 11px; font-weight: 900;
    padding: 2px 7px; border-radius: 999px;
  }
  .seat-row.warn .seat-row__num { color: #9a6d00; }
  .seat-row.full .seat-row__num small { display: none; }
  .seat-row__meta {
    grid-area: meta;
    font-size: 11px; color: var(--sf-muted);
    font-weight: 700;
  }
  @media (min-width: 900px) {
    .seat-row { grid-template-columns: 60px minmax(80px, 1fr) 90px; padding: 11px 14px; }
    .seat-row__time { font-size: 15px; }
    .seat-row__num { font-size: 19px; }
  }

  /* 예약 목록 */
  .pdot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
  .res-row.tr-noshow { opacity: .5; }
  .res-row.tr-noshow .r-name { text-decoration: line-through; }
  .res-row.tr-canceled { opacity: .5; }
  .res-row.tr-canceled .r-name { text-decoration: line-through; }
  .res-row.tr-pending { background: color-mix(in srgb, var(--sf-yellow) 6%, transparent); }
  .res-row.tr-deposited { background: color-mix(in srgb, var(--sf-green) 6%, transparent); }
  .r-acts { display: flex; gap: 2px; justify-content: flex-end; }
  .r-acts button {
    background: transparent; border: 1px solid transparent;
    color: var(--sf-muted); font-size: 15px; padding: 4px 8px;
    border-radius: 8px; min-width: 36px; min-height: 36px; cursor: pointer;
  }
  .r-acts button:hover { color: var(--sf-ink); background: var(--sf-field); }
  .r-acts button.primary { color: var(--sf-river); border-color: color-mix(in srgb, var(--sf-river) 40%, transparent); font-weight: 800; font-size: 12px; padding: 0 10px; }
  .daysum {
    text-align: right; padding: 12px 4px 2px;
    font-size: 13px; color: var(--sf-muted); font-weight: 700;
  }
  .daysum b { color: var(--sf-green); font-size: 15px; font-weight: 900; margin-left: 5px; }
  .hint {
    color: var(--sf-muted); font-size: 12px; margin-top: 12px;
    line-height: 1.5;
    padding: 10px 12px; background: var(--sf-field);
    border-radius: 8px;
  }
  #price-hint { color: var(--sf-river); font-weight: 700; font-size: 12px; margin-left: 4px; }
  .form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .form .field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .form .field label { color: var(--sf-muted); font-size: 12px; font-weight: 800; }
  .form .full { grid-column: 1 / -1; }
  .form input, .form select { min-height: 40px; padding: 8px 10px; }
  .addbtn {
    grid-column: 1 / -1;
    margin-top: 4px;
    min-height: var(--sf-tap);
    background: var(--sf-river); border: 1px solid var(--sf-river);
    color: #fff; font-weight: 900; font-size: 14px; border-radius: 10px;
    cursor: pointer;
  }
  .addbtn:hover { background: var(--sf-river-dark); border-color: var(--sf-river-dark); }
  .savebtn {
    width: 100%; margin-top: 6px;
    min-height: 46px;
    background: var(--sf-river); border: 1px solid var(--sf-river);
    color: #fff; font-weight: 900; font-size: 14px; border-radius: 10px;
    cursor: pointer;
  }
  .savebtn:hover { background: var(--sf-river-dark); border-color: var(--sf-river-dark); }
  .delbtn-modal {
    width: 100%; margin-top: 8px;
    min-height: var(--sf-tap);
    background: transparent; border: 1px solid var(--sf-red);
    color: var(--sf-red); font-weight: 800; font-size: 13px; border-radius: 10px;
    cursor: pointer;
  }
  .delbtn-modal:hover { background: var(--sf-red-soft); }
  .modal-head .t { font-weight: 900; font-size: 15px; }
  .modal-head .x {
    background: transparent; border: 1px solid var(--sf-line);
    color: var(--sf-ink); width: 40px; height: 40px;
    border-radius: 8px; font-size: 16px; cursor: pointer;
  }
  .modal-head .x:hover { background: var(--sf-field); }

  /* 좌석 모달 표 */
  .restable { width: 100%; border-collapse: collapse; }
  .restable thead th {
    text-align: left; padding: 8px 6px; font-size: 12px;
    color: var(--sf-muted); font-weight: 800; border-bottom: 1px solid var(--sf-line-soft);
  }
  .restable tbody td { padding: 10px 6px; border-bottom: 1px solid var(--sf-line-soft); font-size: 13px; }
  .restable tbody tr:hover td { background: var(--sf-field); }
  .tc-nm { font-weight: 800; }
  .tc-meta { color: var(--sf-muted); font-size: 11px; margin-top: 2px; }
  .tc-ppl { text-align: right; font-weight: 800; }
  .tc-amt { text-align: right; }
  .tc-amt .main-amt { color: var(--sf-green); font-weight: 800; font-size: 13px; }
  .tc-amt .dep-amt { color: var(--sf-green); font-size: 11px; margin-top: 2px; }
  .tc-acts { text-align: right; color: var(--sf-muted); }

  .icon { width: 20px; height: 20px; stroke: currentColor; fill: none; stroke-width: 1.8;
          stroke-linecap: round; stroke-linejoin: round; }
</style><script src="/static/admin/surf-admin.js"></script></head>
<body>
<div class="sf-app">
  <aside class="sf-sidebar">
    <div class="sf-brand">서퍼스트<small>운영 콘솔</small></div>
    <nav class="sf-nav" aria-label="관리자 메뉴">
      <a class="sf-nav__link" href="/admin/">
        <svg class="sf-nav__icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h5v-6h4v6h5V10"/></svg>
        <span>홈</span>
      </a>
      <a class="sf-nav__link" href="/availability/admin" aria-current="page">
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
      <div class="sf-topbar__title">예약 관리</div>
      <div class="sf-actions">
        <button class="sf-icon-btn" id="themebtn" type="button" aria-label="테마 전환">
          <svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 109 9 7 7 0 01-9-9z"/></svg>
        </button>
        <a class="sf-btn sf-btn--sm sf-btn--ghost" href="/admin/logout">로그아웃</a>
      </div>
    </header>
    <main class="sf-page">
      <div id="reservation-workbench">
        <div class="sf-page-head">
          <div>
            <div class="sf-eyebrow">예약 관리</div>
            <h1 class="sf-page-title">날짜별 예약 작업대</h1>
            <p class="sf-page-sub">잔여석을 확인하고 예약·입금 상태를 바로 수정합니다.</p>
          </div>
          <div class="sf-actions">
            <button class="sf-btn sf-btn--primary" onclick="focusAddForm()" type="button">예약 추가</button>
            <button class="sf-btn sf-btn--ghost" onclick="loadDay()" type="button">새로고침</button>
          </div>
        </div>

        <section class="sf-panel date-workbar">
          <button class="sf-btn sf-icon-btn" onclick="shiftDay(-1)" type="button">‹</button>
          <input id="date" type="date" onchange="loadDay()">
          <button class="sf-btn sf-icon-btn" onclick="shiftDay(1)" type="button">›</button>
          <button class="sf-btn sf-btn--ghost" onclick="setDay(0)" type="button">오늘</button>
          <button class="sf-btn sf-btn--ghost" onclick="setDay(1)" type="button">내일</button>
          <button class="sf-btn sf-btn--ghost" onclick="setDay(2)" type="button">모레</button>
        </section>

        <div class="reservation-layout">
          <div class="reservation-main">
            <section class="sf-panel seats-panel">
              <div class="panel-headline">
                <h2 class="sf-section-title">잔여석</h2>
                <div class="seats-summary" id="seats-summary" aria-live="polite"></div>
              </div>
              <div class="seat-groups" id="summary"></div>
            </section>

            <section class="sf-panel">
              <div class="panel-headline">
                <h2 class="sf-section-title">예약 타임라인</h2>
                <span class="sf-page-sub" id="listttl">0건</span>
              </div>
              <div id="list"></div>
            </section>
          </div>

          <aside class="sf-panel quick-add-panel" id="quick-add-panel">
            <h2 class="sf-section-title">예약 추가</h2>
            <div class="form sf-form-grid">
              <div class="field sf-field">
                <label>종목</label>
                <select id="f_prog" onchange="onProgChange()"></select>
              </div>
              <div class="field sf-field">
                <label>시간</label>
                <select id="f_time"></select>
                <input id="f_time_txt" placeholder="예: 16:00" style="display:none;">
              </div>
              <div class="field sf-field">
                <label>이름</label>
                <input id="f_name" placeholder="예: 김진수">
              </div>
              <div class="field sf-field">
                <label>인원</label>
                <input id="f_people" type="number" min="1" value="2">
              </div>
              <div class="field sf-field">
                <label>플랫폼</label>
                <select id="f_plat"></select>
              </div>
              <div class="field sf-field">
                <label>결제수단</label>
                <select id="f_pay">
                  <option value="계좌이체">💳 계좌이체</option>
                  <option value="현장카드">💳 현장카드</option>
                  <option value="현금">💵 현금</option>
                </select>
              </div>
              <div class="field sf-field">
                <label>상태</label>
                <select id="f_status">
                  <option value="예약">✅ 예약 확정</option>
                  <option value="입금대기">⏳ 입금대기 (가예약)</option>
                </select>
              </div>
              <div class="field sf-field">
                <label>예약금 (원)</label>
                <input id="f_deposit" type="number" min="0" step="1000" inputmode="numeric" placeholder="예: 20000">
              </div>
              <div class="field sf-field">
                <label>실수령 금액 (원) <span id="price-hint"></span></label>
                <input id="f_amount" type="number" min="0" step="1000" inputmode="numeric" placeholder="예: 80000">
              </div>
              <div class="field full sf-field sf-field--full">
                <label>메모 (사장님 전용 · 손님에게 안 보임)</label>
                <input id="f_memo" placeholder="예: 미입금 / 단체 / 외국인">
              </div>
              <button class="addbtn sf-btn sf-btn--primary" onclick="addRes()" type="button">예약 추가</button>
            </div>
            <div class="hint">건만 추가하면 위 잔여 좌석이 자동으로 합산·마감 처리됩니다.<br>이름·플랫폼·메모는 챗봇/손님에게 절대 안 나갑니다.</div>
          </aside>
        </div>
      </div>
    </main>
  </div>
</div>

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
        <div id="seat-sub" style="color:var(--sf-muted);font-size:12px;margin-top:2px;"></div>
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

function focusAddForm(){
  const panel = $('quick-add-panel');
  const firstField = $('f_name') || $('f_prog');
  if(panel){
    panel.scrollIntoView({behavior:'smooth', block:'start', inline:'nearest'});
  }
  if(firstField && typeof firstField.focus === 'function'){
    window.setTimeout(()=>{
      try { firstField.focus({preventScroll:true}); }
      catch(_err){ firstField.focus(); }
    }, 160);
  }
}

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
  const sumEl = $('seats-summary');
  if(!summary.length){
    el.innerHTML = '<div class="sf-empty">정원 관리 종목 없음</div>';
    if(sumEl) sumEl.textContent = '';
    return;
  }

  // 종목별로 묶기
  const groups = {};
  summary.forEach((s, i) => {
    const key = s.program;
    if(!groups[key]) groups[key] = { program: key, slots: [], cap: 0, booked: 0 };
    groups[key].slots.push({ ...s, _idx: i });
    groups[key].cap += Number(s.capacity) || 0;
    groups[key].booked += Number(s.booked) || 0;
  });

  // 상단 요약: 종목 수 · 총 잔여
  const totalCap = summary.reduce((a, s) => a + (Number(s.capacity) || 0), 0);
  const totalBooked = summary.reduce((a, s) => a + (Number(s.booked) || 0), 0);
  const totalRem = Math.max(totalCap - totalBooked, 0);
  const fullCount = summary.filter(s => s.is_full).length;
  if(sumEl){
    let bits = [`${totalRem}<small>/${totalCap}석 여유</small>`];
    if(fullCount > 0) bits.push(`<span class="sf-status sf-status--full">${fullCount}개 마감</span>`);
    sumEl.innerHTML = bits.join(' · ');
  }

  el.innerHTML = Object.values(groups).map(g => {
    const grp = progGroup(g.program);
    const gRem = Math.max(g.cap - g.booked, 0);
    const gCls = g.booked >= g.cap ? 'full' : (g.booked >= g.cap * 0.8 ? 'warn' : 'ok');
    const gStatus = gCls === 'full' ? { cls: 'full', label: '마감' }
                   : gCls === 'warn' ? { cls: 'pending', label: '주의' }
                   : { cls: 'ok', label: '여유' };
    return `<div class="seat-group grp-${grp}">
      <div class="seat-group__head">
        <div class="seat-group__title">
          <span class="seat-group__dot" aria-hidden="true"></span>
          <b>${esc(g.program)}</b>
        </div>
        <div class="seat-group__meta">
          <span class="seat-group__count">${gRem}<small>/${g.cap}석</small></span>
          <span class="sf-status sf-status--${gStatus.cls}">${gStatus.label}</span>
        </div>
      </div>
      <div class="seat-group__slots">
        ${g.slots.map(s => {
          const cap = Number(s.capacity) || 1;
          const pct = Math.min(100, Math.round((s.booked / cap) * 100));
          const cls = seatClass(s);
          const isClick = s.booked > 0;
          const numHtml = s.is_full
            ? '<span class="seat-row__badge">마감</span>'
            : `${s.remaining}<small>석</small>`;
          return `<button class="seat-row ${cls} ${isClick ? 'clickable' : ''}" onclick="openSeat(${s._idx})" type="button" ${isClick ? '' : 'aria-disabled="true"'}>
            <span class="seat-row__time">${esc(s.time_slot)}</span>
            <span class="seat-row__bar" aria-hidden="true"><span class="seat-row__fill" style="width:${pct}%"></span></span>
            <span class="seat-row__num">${numHtml}</span>
            <span class="seat-row__meta">${s.booked}/${cap}명${isClick ? ' · 명단' : ''}</span>
          </button>`;
        }).join('')}
      </div>
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
  $('listttl').textContent = `${rows.length}건`;
  const el = $('list');
  if(!rows.length){ el.innerHTML = '<div class="sf-empty">이 날짜에 입력된 예약이 없습니다.</div>'; return; }
  let sumAmt = 0;
  const hdr = `<div class="res-hdr"><span class="h-time">시간</span><span class="h-prog">종목</span><span class="h-name">이름</span><span class="h-amt">금액</span><span class="h-acts"></span></div>`;
  const rowsHtml = rows.map(r=>{
    const meta = [r.platform, r.payment_method, r.memo].filter(Boolean).map(esc).join(' · ');
    const st = (r.status||'예약');
    const isNo = st==='노쇼';
    const isPend = st==='입금대기';
    const isCanceled = st==='취소' || st==='예약취소' || st==='취소됨';
    const amt = Number(r.amount)||0; if(st==='예약') sumAmt += amt;
    const dep = Number(r.deposit_amount)||0;
    const hasDeposit = dep > 0;
    const rowCls = isNo ? 'tr-noshow' : (isCanceled ? 'tr-canceled' : (isPend ? 'tr-pending' : (hasDeposit ? 'tr-deposited' : '')));
    let badge = '';
    if(isNo) badge = '<span class="sf-status sf-status--danger">노쇼</span>';
    else if(isCanceled) badge = '<span class="sf-status sf-status--muted">취소</span>';
    else if(isPend) badge = '<span class="sf-status sf-status--pending">입금대기</span>';
    else if(st==='예약') badge = '<span class="sf-status sf-status--ok">예약</span>';
    else badge = `<span class="sf-status sf-status--muted">${esc(st)}</span>`;
    let acts = '';
    if(isNo){
      acts = `<button onclick="setStatus(${r.id},'예약')" title="복원">↩️</button>`;
    } else if(isPend){
      acts = `<button onclick="setStatus(${r.id},'예약')" title="입금확인 → 확정">확정</button>`;
    } else {
      acts = `<button onclick="setStatus(${r.id},'입금대기')" title="입금대기로 전환">⏳</button>`;
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
    + (sumAmt>0?`<div class="daysum">이 날짜 확정 수입 <b>${sumAmt.toLocaleString('ko-KR')}원</b> <small>(입금대기 제외)</small></div>`:'');
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
  fd.append('status', $('f_status').value);
  fd.append('deposit_amount', $('f_deposit').value || '0');
  fd.append('memo', $('f_memo').value.trim());
  fd.append('amount', $('f_amount').value || '0');
  const res = await fetch('api/reservations', {method:'POST', body:fd});
  if(!res.ok){
    const t = await res.text();
    alert('예약 추가 실패 ('+res.status+')\\n'+t.slice(0,500));
    return;
  }
  $('f_name').value=''; $('f_memo').value=''; $('f_people').value='2'; $('f_amount').value=''; $('f_deposit').value=''; $('f_pay').value='계좌이체'; $('f_status').value='예약';
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
  if(status==='입금대기') msg = '입금대기(가예약)로 전환할까요?\\n자리는 잡아두지만 입금 확인 전까지 수입엔 안 잡힙니다.';
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
  body.innerHTML = rows.length ? `<div style="overflow-x:auto;"><table class="restable">
    <thead><tr><th>이름</th><th>인원</th><th>금액</th><th></th></tr></thead>
    <tbody>${rows.map(r=>{
      const meta = [r.platform, r.payment_method, r.memo].filter(Boolean).map(esc).join(' · ');
      const amt = Number(r.amount)||0;
      const dep = Number(r.deposit_amount)||0;
      return `<tr onclick="closeSeat();openEdit(${r.id})" style="cursor:pointer">
        <td><div class="tc-nm">${esc(r.customer_name)||'(이름없음)'}</div>${meta?`<div class="tc-meta">${meta}</div>`:''}</td>
        <td class="tc-ppl">${r.people}<small style="font-size:12px;color:var(--sub)">명</small></td>
        <td class="tc-amt">${amt>0?`<div class="main-amt">${amt.toLocaleString('ko-KR')}원</div>`:''}${dep>0?`<div class="dep-amt">예약금 ${dep.toLocaleString('ko-KR')}원</div>`:''}</td>
        <td class="tc-acts">›</td>
      </tr>`;
    }).join('')}</tbody>
  </table></div>` : '<div class="sf-empty">이 시간대 예약이 없습니다.</div>';
  $('seatmodal').classList.add('show');
}
function closeSeat(){ $('seatmodal').classList.remove('show'); }

document.addEventListener('keydown', e=>{ if(e.key==='Escape'){ closeEdit(); closeSeat(); } });

init();
</script>
<script>SurfAdmin.initTheme('themebtn');</script>
<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js');</script>
</body></html>"""
