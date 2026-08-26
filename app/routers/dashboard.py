"""오너용 분석 대시보드 (/dashboard/)."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routers.admin import require_admin
from app.services.auth import verify_session
from app.services.db import select_all

logger = logging.getLogger(__name__)
router = APIRouter()
KST = timezone(timedelta(hours=9))


def _amt(v) -> int:
    if v is None:
        return 0
    try:
        return max(int(float(str(v).replace(",", "").replace("원", "").strip() or "0")), 0)
    except (ValueError, TypeError):
        return 0


@router.get("/api/analytics")
async def api_analytics(_=Depends(require_admin)):
    try:
        rows = await select_all(
            "reservations",
            "slot_date,program,time_slot,people,platform,amount,payment_method,status",
        )
    except Exception as e:
        logger.error(f"analytics 조회 실패: {e}")
        return {}

    confirmed = [r for r in rows if (r.get("status") or "예약") == "예약"]
    noshow_count = sum(1 for r in rows if (r.get("status") or "예약") == "노쇼")
    pending_count = sum(1 for r in rows if (r.get("status") or "예약") == "입금대기")

    def agg_by(key_fn):
        out: dict = {}
        for r in confirmed:
            k = key_fn(r)
            if k not in out:
                out[k] = {"count": 0, "people": 0, "amount": 0}
            out[k]["count"] += 1
            out[k]["people"] += int(r.get("people") or 0)
            out[k]["amount"] += _amt(r.get("amount"))
        return out

    platform_map = agg_by(lambda r: r.get("platform") or "현장")
    prog_map = agg_by(lambda r: r.get("program") or "기타")

    monthly: dict = {}
    monthly_ppl: dict = {}
    for r in confirmed:
        m = (r.get("slot_date") or "")[:7]
        if m:
            monthly[m] = monthly.get(m, 0) + _amt(r.get("amount"))
            monthly_ppl[m] = monthly_ppl.get(m, 0) + int(r.get("people") or 0)

    today = datetime.now(KST).date()
    cutoff = str(today - timedelta(days=89))
    daily: dict = {}
    daily_ppl: dict = {}
    for r in confirmed:
        d = r.get("slot_date") or ""
        if d >= cutoff:
            daily[d] = daily.get(d, 0) + _amt(r.get("amount"))
            daily_ppl[d] = daily_ppl.get(d, 0) + int(r.get("people") or 0)

    cal: dict = {}
    for r in confirmed:
        d = r.get("slot_date") or ""
        if d:
            if d not in cal:
                cal[d] = {"count": 0, "people": 0, "amount": 0}
            cal[d]["count"] += 1
            cal[d]["people"] += int(r.get("people") or 0)
            cal[d]["amount"] += _amt(r.get("amount"))

    today_s = str(today)
    ym = today_s[:7]

    # 노쇼율: 지난 날짜 기준. status '예약'인 과거 건은 방문 완료로 간주(운영 컨벤션).
    past_visited = sum(
        1 for r in rows
        if (r.get("status") or "예약") == "예약" and (r.get("slot_date") or "") < today_s
    )
    past_noshow = sum(
        1 for r in rows
        if (r.get("status") or "예약") == "노쇼" and (r.get("slot_date") or "") < today_s
    )
    past_total = past_visited + past_noshow
    noshow_rate = round(past_noshow / past_total * 100, 1) if past_total else None

    total_ppl = sum(int(r.get("people") or 0) for r in confirmed)
    total_rev = sum(_amt(r.get("amount")) for r in confirmed)
    today_ppl = sum(int(r.get("people") or 0) for r in confirmed if r.get("slot_date") == today_s)
    today_rev = sum(_amt(r.get("amount")) for r in confirmed if r.get("slot_date") == today_s)
    month_ppl = sum(int(r.get("people") or 0) for r in confirmed if (r.get("slot_date") or "")[:7] == ym)
    month_rev = sum(_amt(r.get("amount")) for r in confirmed if (r.get("slot_date") or "")[:7] == ym)

    return {
        "platform": platform_map,
        "program": prog_map,
        "monthly": monthly,
        "monthly_ppl": monthly_ppl,
        "daily": daily,
        "daily_ppl": daily_ppl,
        "calendar": cal,
        "today": today_s,
        "stats": {
            "confirmed": len(confirmed),
            "noshow": noshow_count,
            "noshow_rate": noshow_rate,
            "past_total": past_total,
            "pending": pending_count,
            "total_ppl": total_ppl,
            "total_rev": total_rev,
            "today_ppl": today_ppl,
            "today_rev": today_rev,
            "month_ppl": month_ppl,
            "month_rev": month_rev,
            "month": ym,
        },
    }


CSS_VER = "20260826-redesign"


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard_page(asess: str | None = Cookie(default=None)):
    if not verify_session(asess):
        return RedirectResponse(url="/admin/login", status_code=302)
    return HTMLResponse(DASHBOARD_HTML.replace("{CSS_VER}", CSS_VER))


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#09090d" media="(prefers-color-scheme: dark)">
<link rel="stylesheet" href="/static/admin/surf-admin.css?v={CSS_VER}">
<title>서퍼스트 · 분석</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="/static/admin/surf-admin.js"></script>
<style>
  /* 분석 화면 전용: 차트/캘린더/표 */
  .kgrid {
    display: grid; grid-template-columns: repeat(2, 1fr);
    gap: 8px; margin-bottom: 14px;
  }
  @media(min-width: 900px) { .kgrid { grid-template-columns: repeat(4, 1fr); gap: 12px; } }
  .kcard {
    background: var(--sf-surface); border: 1px solid var(--sf-line-soft);
    border-radius: var(--sf-radius); padding: 12px 14px;
    box-shadow: var(--sf-shadow);
    position: relative; overflow: hidden;
  }
  .kcard::before {
    content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--sf-line);
  }
  .kcard.accent::before { background: var(--sf-river); }
  .kcard.green::before { background: var(--sf-green); }
  .kcard.warn::before { background: var(--sf-yellow); }
  .kcard .kl { font-size: 11px; font-weight: 800; color: var(--sf-muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: .04em; }
  .kcard .kv { font-size: 22px; font-weight: 950; line-height: 1; letter-spacing: -0.02em; }
  .kcard .ks { font-size: 11px; color: var(--sf-muted); margin-top: 6px; font-weight: 600; }
  .kcard.accent .kv { color: var(--sf-river); }
  .kcard.green .kv { color: var(--sf-green); }
  .kcard.warn .kv { color: #7a5100; }
  @media(min-width: 900px) { .kcard .kv { font-size: 26px; } }

  .crow { display: grid; grid-template-columns: 1fr; gap: 10px; margin-bottom: 14px; }
  @media(min-width: 900px) { .crow.r2 { grid-template-columns: 3fr 2fr; } }
  .cbox {
    background: var(--sf-surface); border: 1px solid var(--sf-line-soft);
    border-radius: var(--sf-radius); padding: 14px;
    box-shadow: var(--sf-shadow); margin-bottom: 12px;
  }
  .cbox:last-child { margin-bottom: 0; }
  .cl {
    font-size: 13px; font-weight: 800; color: var(--sf-ink); margin-bottom: 12px;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 6px;
  }
  .rbtns { display: flex; gap: 4px; }
  .rbtn {
    background: var(--sf-surface); border: 1px solid var(--sf-line);
    color: var(--sf-muted); border-radius: 999px;
    font-size: 12px; font-weight: 800; padding: 6px 12px;
    min-height: 32px; cursor: pointer;
  }
  .rbtn.on { background: var(--sf-navy); color: #fff; border-color: var(--sf-navy); }

  .tbl-wrap { overflow-x: auto; margin-top: 10px; }
  .tbl-wrap table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .tbl-wrap th {
    color: var(--sf-muted); font-size: 10px; font-weight: 800; padding: 6px 6px;
    border-bottom: 1px solid var(--sf-line-soft);
    text-align: left; white-space: nowrap; text-transform: uppercase;
  }
  .tbl-wrap td { padding: 8px 6px; border-bottom: 1px solid var(--sf-line-soft); vertical-align: middle; }
  .tbl-wrap tr:last-child td { border-bottom: 0; }
  .tbl-wrap .fw { font-weight: 800; }
  .tbl-wrap .tr { text-align: right; }
  .bar-wrap { display: inline-block; width: 50px; vertical-align: middle; background: var(--sf-line-soft); border-radius: 3px; overflow: hidden; }
  .bar { height: 5px; border-radius: 3px; background: var(--sf-river); }

  .two { display: grid; grid-template-columns: 1fr; gap: 12px; }
  @media(min-width: 900px) { .two { grid-template-columns: 1fr 1fr; } }

  .cal-wrap {
    background: var(--sf-surface); border: 1px solid var(--sf-line-soft);
    border-radius: var(--sf-radius); padding: 14px;
    box-shadow: var(--sf-shadow);
  }
  .cal-nav { display: flex; align-items: center; justify-content: center; gap: 14px; margin-bottom: 12px; }
  .cnbtn {
    background: var(--sf-surface); border: 1px solid var(--sf-line);
    color: var(--sf-ink); width: 36px; height: 36px; border-radius: 8px;
    cursor: pointer; font-size: 16px;
    display: flex; align-items: center; justify-content: center;
  }
  .cnbtn:hover { background: var(--sf-field); }
  .ctitle { font-size: 15px; font-weight: 900; min-width: 120px; text-align: center; letter-spacing: -0.01em; }
  .cgrid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
  .chd { text-align: center; font-size: 10px; font-weight: 800; color: var(--sf-muted); padding: 4px 0; }
  .ccell {
    aspect-ratio: 1; border-radius: 8px; border: 1px solid var(--sf-line-soft);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    cursor: pointer; transition: border-color .12s;
    background: color-mix(in srgb, var(--sf-river) calc(var(--ca, 0) * 100%), transparent);
  }
  .ccell:hover { border-color: var(--sf-river); }
  .ccell.today .cday {
    background: var(--sf-river); color: #fff; border-radius: 50%;
    width: 20px; height: 20px;
    display: flex; align-items: center; justify-content: center;
  }
  .ccell.sun .cday { color: var(--sf-red); }
  .ccell.sat .cday { color: var(--sf-river); }
  .ccell.off { background: var(--sf-bg); border-color: transparent; cursor: default; }
  .ccell.off:hover { border-color: transparent; }
  .cday { font-size: 12px; font-weight: 800; line-height: 1; }
  .cppl { font-size: 10px; font-weight: 700; color: var(--sf-muted); margin-top: 2px; line-height: 1; }
  .ccell.has .cppl { color: var(--sf-ink); }
  .cdet {
    margin-top: 12px;
    background: color-mix(in srgb, var(--sf-river) 8%, var(--sf-surface));
    border: 1px solid color-mix(in srgb, var(--sf-river) 35%, transparent);
    border-radius: 10px; padding: 12px 14px; display: none;
  }
  .cdet.show { display: block; }
  .cddate { font-size: 12px; font-weight: 800; color: var(--sf-river); margin-bottom: 6px; }
  .cdet-row { display: flex; gap: 20px; flex-wrap: wrap; }
  .dm .dk { font-size: 10px; font-weight: 800; color: var(--sf-muted); margin-bottom: 3px; }
  .dm .dv { font-size: 18px; font-weight: 900; letter-spacing: -0.02em; }

  .loading { color: var(--sf-muted); padding: 32px; text-align: center; font-size: 13px; }
  @media(max-width: 480px) {
    .kcard .kv { font-size: 20px; }
    .cgrid { gap: 2px; }
    .ccell { border-radius: 6px; }
    .cday { font-size: 11px; }
    .cppl { font-size: 9px; }
  }
</style>
</head>
<body>
<div class="sf-app">
  <aside class="sf-sidebar">
    <div class="sf-brand">서퍼스트<small>운영 콘솔</small></div>
    <nav class="sf-nav" aria-label="관리자 메뉴">
      <a class="sf-nav__link" href="/admin/">
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
      <a class="sf-nav__link" href="/dashboard/" aria-current="page">
        <svg class="sf-nav__icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>
        <span>분석</span>
      </a>
    </nav>
  </aside>
  <div class="sf-main">
    <header class="sf-topbar">
      <div class="sf-topbar__title">영업 리포트</div>
      <div class="sf-actions">
        <button class="sf-icon-btn" id="themebtn" type="button" aria-label="테마 전환">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3a9 9 0 109 9 7 7 0 01-9-9z"/></svg>
        </button>
        <button class="sf-icon-btn" onclick="reload()" aria-label="새로고침" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 12a9 9 0 0115.5-6.3L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 01-15.5 6.3L3 16"/><path d="M3 21v-5h5"/></svg>
        </button>
        <a class="sf-btn sf-btn--sm sf-btn--ghost" href="/admin/logout">로그아웃</a>
      </div>
    </header>
    <main class="sf-page">
      <div id="analytics-report">
        <div class="sf-page-head">
          <div>
            <div class="sf-eyebrow">분석</div>
            <h1 class="sf-page-title">영업 리포트</h1>
            <p class="sf-page-sub">매출·채널·종목·요일 흐름을 한눈에.</p>
          </div>
        </div>
        <div class="report-tabs">
          <button class="report-tab on" data-tab="ov" onclick="sw('ov')" type="button">개요</button>
          <button class="report-tab" data-tab="ch" onclick="sw('ch')" type="button">채널·종목</button>
          <button class="report-tab" data-tab="cal" onclick="sw('cal')" type="button">캘린더</button>
        </div>

  <!-- ===== TAB: 개요 ===== -->
  <div id="p-ov">
    <div class="kgrid" id="kgrid"><div class="loading">불러오는 중…</div></div>
    <div class="crow r2">
      <div class="cbox" style="margin-bottom:0">
        <div class="cl">월별 수입 추이 (최근 12개월, 만원)</div>
        <canvas id="mchart"></canvas>
      </div>
      <div class="cbox" style="margin-bottom:0">
        <div class="cl">요일별 평균 방문 인원</div>
        <canvas id="dchart"></canvas>
      </div>
    </div>
    <div style="height:14px"></div>
    <div class="cbox">
      <div class="cl">
        일별 방문 인원
        <div class="rbtns">
          <button class="rbtn on" data-range="30" onclick="setRange(30)">30일</button>
          <button class="rbtn" data-range="60" onclick="setRange(60)">60일</button>
          <button class="rbtn" data-range="90" onclick="setRange(90)">90일</button>
        </div>
      </div>
      <canvas id="lchart" height="100"></canvas>
    </div>
  </div>

  <!-- ===== TAB: 채널·종목 ===== -->
  <div id="p-ch" style="display:none">
    <div class="two">
      <div class="cbox">
        <div class="cl">채널별 매출 비율</div>
        <canvas id="pltchart" height="200"></canvas>
        <div class="tbl-wrap" id="plt-tbl"></div>
      </div>
      <div class="cbox">
        <div class="cl">종목별 매출 비율</div>
        <canvas id="prgchart" height="200"></canvas>
        <div class="tbl-wrap" id="prg-tbl"></div>
      </div>
    </div>
  </div>

  <!-- ===== TAB: 캘린더 ===== -->
  <div id="p-cal" style="display:none">
    <div class="cal-wrap">
      <div class="cal-nav">
        <button class="cnbtn" onclick="calMove(-1)">‹</button>
        <div class="ctitle" id="ctitle"></div>
        <button class="cnbtn" onclick="calMove(1)">›</button>
      </div>
      <div class="cgrid" id="cgrid"></div>
      <div class="cdet" id="cdet">
        <div class="cddate" id="cdet-date"></div>
        <div class="cdet-row" id="cdet-row"></div>
      </div>
    </div>
  </div>
      </div>

</main>
  </div>
</div>
<script>
/* ===== UTILS ===== */
const $ = id => document.getElementById(id);
function won(n) { return (Number(n)||0).toLocaleString('ko-KR') + '원'; }
function pad(n) { return String(n).padStart(2,'0'); }
function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function isDark() { return document.documentElement.getAttribute('data-theme') === 'dark'; }
function tc() { return isDark() ? '#6b7280' : '#57606a'; }
function gc() { return isDark() ? 'rgba(255,255,255,.05)' : 'rgba(0,0,0,.05)'; }
function COLORS() {
  // 서퍼스트 브랜드 팔레트 (river 톤 우선)
  return isDark()
    ? ['#39b8c7','#4fc890','#f5c25b','#ef6b5f','#70a8ff','#a994ff','#ff9a5b','#9db4be']
    : ['#0e8fa3','#128757','#e5a318','#cc4436','#2f6fdb','#7657d6','#e07a2b','#5c7079'];
}

/* ===== TABS ===== */
function sw(tab) {
  document.querySelectorAll('[id^="p-"]').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.report-tab').forEach(b => b.classList.remove('on'));
  $('p-' + tab).style.display = '';
  document.querySelector('[data-tab="' + tab + '"]').classList.add('on');
  if (tab === 'cal' && D && !_calInit) { _calInit = true; initCal(); }
}

/* ===== STATE ===== */
let D = null;
let _calInit = false;
let _calY, _calM;
let _range = 30;
const _charts = {};

/* ===== CHART HELPER ===== */
function mkChart(id, config) {
  if (typeof Chart === 'undefined') return;
  const el = $(id);
  if (!el) return;
  if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; }
  _charts[id] = new Chart(el, config);
}

/* ===== LOAD ===== */
async function load() {
  try {
    const r = await fetch('api/analytics');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    D = await r.json();
    renderAll();
  } catch(e) {
    console.error(e);
    $('kgrid').innerHTML = '<div class="sf-empty">데이터를 불러오지 못했습니다.<br>새로고침해 주세요.</div>';
  }
}

function reload() { D = null; _calInit = false; load(); }

function renderAll() {
  renderKPI();
  renderMonthChart();
  renderDOWChart();
  renderDailyChart();
  renderChannels();
  if (_calInit) buildCal();
}

/* ===== KPI ===== */
function renderKPI() {
  const s = D.stats || {};
  const ym = (s.month || '').slice(0,4) + '년 ' + (s.month || '').slice(5) + '월';
  $('kgrid').innerHTML = `
    <div class="kcard accent">
      <div class="kl">오늘 방문 인원</div>
      <div class="kv">${s.today_ppl||0}명</div>
      <div class="ks">${won(s.today_rev)}</div>
    </div>
    <div class="kcard warn">
      <div class="kl">${ym} 수입</div>
      <div class="kv" style="font-size:18px">${won(s.month_rev)}</div>
      <div class="ks">${s.month_ppl||0}명 방문</div>
    </div>
    <div class="kcard green">
      <div class="kl">전체 확정 예약</div>
      <div class="kv">${s.confirmed||0}건</div>
      <div class="ks">누적 ${s.total_ppl||0}명</div>
    </div>
    <div class="kcard">
      <div class="kl">전체 누적 수입</div>
      <div class="kv" style="font-size:18px">${won(s.total_rev)}</div>
      <div class="ks">입금대기 ${s.pending||0}건</div>
    </div>`;
}

/* ===== MONTHLY BAR ===== */
function renderMonthChart() {
  const m = D.monthly || {};
  const today = D.today || new Date().toISOString().slice(0,10);
  const base = new Date(today + 'T00:00:00');
  const months = [];
  for (let i = 11; i >= 0; i--) {
    const d = new Date(base.getFullYear(), base.getMonth() - i, 1);
    months.push(d.getFullYear() + '-' + pad(d.getMonth() + 1));
  }
  const data = months.map(k => +((m[k]||0)/10000).toFixed(1));
  const dark = isDark();
  const main = dark ? '#39b8c7' : '#0e8fa3';
  const dim  = dark ? 'rgba(57,184,199,.18)' : 'rgba(14,143,163,.14)';
  mkChart('mchart', {
    type: 'bar',
    data: {
      labels: months.map(mo => mo.slice(5) + '월'),
      datasets: [{ data, backgroundColor: months.map((_,i) => i===11?main:dim), borderRadius: 7, borderSkipped: false }]
    },
    options: {
      plugins: { legend:{display:false}, tooltip:{callbacks:{label:c=>c.raw+'만원'}} },
      scales: {
        y: { ticks:{color:tc(),callback:v=>v+'만'}, grid:{color:gc()}, beginAtZero:true, border:{display:false} },
        x: { ticks:{color:tc()}, grid:{display:false}, border:{display:false} }
      }
    }
  });
}

/* ===== DOW BAR ===== */
function renderDOWChart() {
  const dp = D.daily_ppl || {};
  const DOW = ['일','월','화','수','목','금','토'];
  const sumP = [0,0,0,0,0,0,0];
  const cnt  = [0,0,0,0,0,0,0];
  Object.entries(dp).forEach(([d, p]) => {
    const day = new Date(d + 'T00:00:00').getDay();
    sumP[day] += p; cnt[day]++;
  });
  const avg = sumP.map((s, i) => cnt[i] > 0 ? +(s/cnt[i]).toFixed(1) : 0);
  const C = isDark() ? '#39b8c7' : '#0e8fa3';
  mkChart('dchart', {
    type: 'bar',
    data: { labels: DOW, datasets: [{ data: avg, backgroundColor: C, borderRadius: 6, borderSkipped: false }] },
    options: {
      plugins: { legend:{display:false}, tooltip:{callbacks:{label:c=>c.raw+'명 평균'}} },
      scales: {
        y: { ticks:{color:tc()}, grid:{color:gc()}, beginAtZero:true, border:{display:false} },
        x: { ticks:{color:tc()}, grid:{display:false}, border:{display:false} }
      }
    }
  });
}

/* ===== DAILY LINE ===== */
function setRange(n) {
  _range = n;
  document.querySelectorAll('.rbtn').forEach(b => b.classList.toggle('on', Number(b.dataset.range) === n));
  if (D) renderDailyChart();
}

function renderDailyChart() {
  const dp = D.daily_ppl || {};
  const today = D.today || new Date().toISOString().slice(0,10);
  const labels = [], data = [];
  for (let i = _range - 1; i >= 0; i--) {
    const d = new Date(today + 'T00:00:00');
    d.setDate(d.getDate() - i);
    const key = d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate());
    labels.push((d.getMonth()+1) + '/' + d.getDate());
    data.push(dp[key] || 0);
  }
  const dark = isDark();
  const lineC = dark ? '#39b8c7' : '#0e8fa3';
  const fillC = dark ? 'rgba(57,184,199,.14)' : 'rgba(14,143,163,.1)';
  mkChart('lchart', {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data, borderColor: lineC, backgroundColor: fillC,
        fill: true, tension: 0.35, borderWidth: 2,
        pointRadius: _range <= 30 ? 3 : 0,
        pointBackgroundColor: lineC
      }]
    },
    options: {
      plugins: { legend:{display:false}, tooltip:{callbacks:{label:c=>c.raw+'명'}} },
      scales: {
        y: { ticks:{color:tc()}, grid:{color:gc()}, beginAtZero:true, border:{display:false} },
        x: { ticks:{color:tc(), maxTicksLimit: _range<=30?10:8, maxRotation:0}, grid:{display:false}, border:{display:false} }
      }
    }
  });
}

/* ===== CHANNELS ===== */
function renderChannels() {
  if (!D) return;
  renderDonut('pltchart', D.platform || {}, 'plt-tbl');
  renderDonut('prgchart', D.program || {}, 'prg-tbl');
}

function renderDonut(chartId, dataMap, tblId) {
  const entries = Object.entries(dataMap).sort((a,b) => b[1].amount - a[1].amount);
  const tblEl = $(tblId);
  if (!entries.length) {
    if (tblEl) tblEl.innerHTML = '<div class="sf-empty" style="margin-top:12px">데이터 없음</div>';
    return;
  }
  const labels = entries.map(e => e[0]);
  const amounts = entries.map(e => e[1].amount);
  const totalAmt = amounts.reduce((s,v) => s+v, 0);
  const C = COLORS();
  const dark = isDark();
  mkChart(chartId, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data: amounts, backgroundColor: C, borderWidth: 3, borderColor: dark?'#0d2029':'#ffffff', hoverOffset: 8 }]
    },
    options: {
      plugins: {
        legend: { position:'bottom', labels:{color:tc(),font:{size:12},padding:10,boxWidth:10,boxHeight:10,borderRadius:3,useBorderRadius:true} },
        tooltip: { callbacks: { label: ctx => ctx.label + ' · ' + won(ctx.raw) + ' (' + (totalAmt?Math.round(ctx.raw/totalAmt*100):0) + '%)' } }
      },
      cutout: '62%'
    }
  });
  if (!tblEl) return;
  tblEl.innerHTML = `<table>
    <thead><tr><th>이름</th><th class="tr">건수</th><th class="tr">인원</th><th class="tr">매출</th><th>비율</th></tr></thead>
    <tbody>${entries.map((e,i) => {
      const [name, v] = e;
      const pct = totalAmt ? Math.round(v.amount/totalAmt*100) : 0;
      return `<tr>
        <td class="fw"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${C[i%C.length]};margin-right:5px;vertical-align:middle"></span>${esc(name)}</td>
        <td class="tr">${v.count}건</td>
        <td class="tr">${v.people}명</td>
        <td class="tr fw">${won(v.amount)}</td>
        <td><div class="bar-wrap"><div class="bar" style="width:${pct}%"></div></div> <span style="font-size:12px;color:var(--sub)">${pct}%</span></td>
      </tr>`;
    }).join('')}</tbody>
  </table>`;
}

/* ===== CALENDAR ===== */
function initCal() {
  const today = new Date((D.today || new Date().toISOString().slice(0,10)) + 'T00:00:00');
  _calY = today.getFullYear();
  _calM = today.getMonth() + 1;
  buildCal();
}

function calMove(delta) {
  _calM += delta;
  if (_calM > 12) { _calM = 1; _calY++; }
  if (_calM < 1)  { _calM = 12; _calY--; }
  $('cdet').classList.remove('show');
  buildCal();
}

function buildCal() {
  $('ctitle').textContent = _calY + '년 ' + _calM + '월';
  const cal = (D && D.calendar) || {};
  const today = (D && D.today) || '';
  const daysInMonth = new Date(_calY, _calM, 0).getDate();
  const firstDay = new Date(_calY, _calM - 1, 1).getDay();

  let maxP = 1;
  for (let d = 1; d <= daysInMonth; d++) {
    const v = cal[_calY + '-' + pad(_calM) + '-' + pad(d)];
    if (v && v.people > maxP) maxP = v.people;
  }

  const DOW = ['일','월','화','수','목','금','토'];
  let html = DOW.map(w => `<div class="chd">${w}</div>`).join('');
  for (let i = 0; i < firstDay; i++) html += '<div class="ccell off"></div>';

  for (let d = 1; d <= daysInMonth; d++) {
    const key = _calY + '-' + pad(_calM) + '-' + pad(d);
    const v = cal[key];
    const dow = (firstDay + d - 1) % 7;
    const a = v ? (0.15 + (v.people / maxP) * 0.7).toFixed(2) : '0';
    let cls = 'ccell';
    if (key === today) cls += ' today';
    if (dow === 0) cls += ' sun';
    if (dow === 6) cls += ' sat';
    if (v) cls += ' has';
    html += `<div class="${cls}" style="--ca:${a}" onclick="calClick('${key}')">
      <span class="cday">${d}</span>
      ${v ? `<span class="cppl">${v.people}명</span>` : ''}
    </div>`;
  }
  $('cgrid').innerHTML = html;
}

function calClick(key) {
  const v = ((D && D.calendar) || {})[key];
  const det = $('cdet');
  if (!v) { det.classList.remove('show'); return; }
  $('cdet-date').textContent = key.slice(0,4) + '년 ' + key.slice(5,7) + '월 ' + key.slice(8) + '일';
  $('cdet-row').innerHTML = `
    <div class="dm"><div class="dk">예약 건수</div><div class="dv">${v.count}건</div></div>
    <div class="dm"><div class="dk">방문 인원</div><div class="dv">${v.people}명</div></div>
    <div class="dm"><div class="dk">당일 수입</div><div class="dv" style="font-size:16px">${won(v.amount)}</div></div>`;
  det.classList.add('show');
}

load();
</script>
<script>
SurfAdmin.initTheme('themebtn');
document.getElementById('themebtn').addEventListener('click', function(){
  if (D) renderAll();
});
</script>
</body>
</html>"""
