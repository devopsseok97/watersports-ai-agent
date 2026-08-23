# Surfirst Admin Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Surfirst admin pages into a shared, mobile-first field operations console without changing backend behavior or the OSON landing page.

**Architecture:** Keep the existing FastAPI HTML-string route pattern, but move shared admin visual language and utilities into `static/admin/surf-admin.css` and `static/admin/surf-admin.js`. Each route keeps its page-specific JavaScript and API calls while adopting the same shell, navigation, tokens, status badges, buttons, and responsive rules.

**Tech Stack:** Python 3, FastAPI, static HTML/CSS/JavaScript, Chart.js from CDN on chart pages, pytest, FastAPI TestClient.

**Spec:** `docs/superpowers/specs/2026-08-23-surfirst-admin-redesign-design.md`

## Global Constraints

- Scope includes `/admin/`, `/availability/admin`, `/dashboard/`, `/photos/admin`, and `/admin/login`.
- Scope excludes `/` OSON landing page, Kakao webhook behavior, reservation APIs, photo upload APIs, Supabase schema, React/Vue migration, chart library replacement, and reservation policy changes.
- Use shared admin assets at `static/admin/surf-admin.css` and `static/admin/surf-admin.js`.
- Preserve dark theme support using shared token variants.
- Use system Korean fonts: `-apple-system`, `Apple SD Gothic Neo`, `Malgun Gothic`.
- Apply `font-variant-numeric: tabular-nums` for numeric UI.
- Navigation labels are `홈`, `예약`, `사진`, `분석`.
- All buttons need at least 40px touch target sizing.
- State must not be conveyed by color alone; use text labels for reservation, pending payment, full, no-show, warning, and danger states.
- Do not redesign `static/landing/index.html`.

---

## File Structure

- Create `static/admin/surf-admin.css`: shared Surfirst admin design tokens, dark theme, shell layout, nav, buttons, panels, metric cards, status badges, tables, modals, forms, empty states, responsive rules, focus styles.
- Create `static/admin/surf-admin.js`: shared theme functions, date formatting, currency formatting, HTML escaping, nav active helper, and small DOM helpers.
- Modify `app/routers/admin.py`: login page redesign, admin home shell markup, remove duplicated base CSS, keep home page data loading and modals, reshape home sections around today operations.
- Modify `app/routers/availability.py`: adopt shared shell, preserve reservation APIs and form fields, reshape reservation screen into date bar, slot board, quick add panel, and timeline list.
- Modify `app/routers/photos.py`: adopt shared shell, preserve album APIs, reshape album create and upload flow, add visible upload status text.
- Modify `app/routers/dashboard.py`: adopt shared shell, preserve `/api/analytics` and Chart.js rendering, restyle charts/tabs/tables as reports.
- Create `tests/test_admin_ui_assets.py`: verify shared assets are served, admin HTML references shared assets, nav labels exist, and OSON landing does not reference admin assets.

---

### Task 1: Shared Admin Assets

**Files:**
- Create: `static/admin/surf-admin.css`
- Create: `static/admin/surf-admin.js`
- Create: `tests/test_admin_ui_assets.py`

**Interfaces:**
- Consumes: FastAPI static mount already defined in `app/main.py`.
- Produces:
  - CSS classes: `sf-app`, `sf-sidebar`, `sf-topbar`, `sf-nav`, `sf-nav__link`, `sf-page`, `sf-page-head`, `sf-actions`, `sf-panel`, `sf-card-grid`, `sf-metric`, `sf-status`, `sf-btn`, `sf-btn--primary`, `sf-btn--ghost`, `sf-btn--danger`, `sf-form-grid`, `sf-empty`, `sf-modal-bg`, `sf-modal`.
  - JavaScript global: `window.SurfAdmin` with `applyTheme(theme)`, `toggleTheme()`, `initTheme(buttonId)`, `fmtDateTime(value)`, `won(value)`, `esc(value)`, `todayLabel()`.

- [ ] **Step 1: Write failing asset tests**

Add `tests/test_admin_ui_assets.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_shared_admin_css_served():
    response = client.get("/static/admin/surf-admin.css")
    assert response.status_code == 200
    assert "--sf-river" in response.text
    assert ".sf-app" in response.text


def test_shared_admin_js_served():
    response = client.get("/static/admin/surf-admin.js")
    assert response.status_code == 200
    assert "window.SurfAdmin" in response.text
    assert "toggleTheme" in response.text


def test_landing_does_not_reference_admin_assets():
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/admin/surf-admin.css" not in response.text
    assert "/static/admin/surf-admin.js" not in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_admin_ui_assets.py -v`

Expected: first two tests fail with 404 for missing shared admin assets.

- [ ] **Step 3: Create shared CSS**

Create `static/admin/surf-admin.css` with this structure:

```css
:root {
  --sf-bg: #f4f8fa;
  --sf-surface: #ffffff;
  --sf-surface-raised: #f9fcfd;
  --sf-ink: #17242b;
  --sf-muted: #667780;
  --sf-line: #d9e4e8;
  --sf-navy: #12313f;
  --sf-river: #0e8fa3;
  --sf-yellow: #f4b740;
  --sf-green: #168a5b;
  --sf-red: #d94a3a;
  --sf-blue: #2f6fdb;
  --sf-purple: #7657d6;
  --sf-field: #eef5f7;
  --sf-shadow: 0 12px 30px rgba(18, 49, 63, .08);
}

[data-theme="dark"] {
  --sf-bg: #07161d;
  --sf-surface: #0d2029;
  --sf-surface-raised: #102a34;
  --sf-ink: #edf7f9;
  --sf-muted: #8ea5ae;
  --sf-line: #1f3a45;
  --sf-navy: #071219;
  --sf-river: #39b8c7;
  --sf-yellow: #f5c25b;
  --sf-green: #45c78a;
  --sf-red: #ee6b5f;
  --sf-blue: #70a8ff;
  --sf-purple: #a994ff;
  --sf-field: #0a1b23;
  --sf-shadow: none;
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--sf-bg);
  color: var(--sf-ink);
  font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  font-size: 16px;
  line-height: 1.45;
  font-variant-numeric: tabular-nums;
}
a, button, input, select, textarea { font: inherit; }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible {
  outline: 3px solid rgba(14, 143, 163, .35);
  outline-offset: 2px;
}

.sf-app { min-height: 100svh; display: grid; grid-template-columns: 216px minmax(0, 1fr); }
.sf-sidebar { background: var(--sf-navy); color: #fff; padding: 18px 14px; position: sticky; top: 0; height: 100svh; }
.sf-brand { font-weight: 900; font-size: 20px; letter-spacing: 0; }
.sf-brand small { display: block; color: rgba(255,255,255,.62); font-size: 12px; margin-top: 4px; font-weight: 700; }
.sf-nav { display: grid; gap: 6px; margin-top: 24px; }
.sf-nav__link { color: rgba(255,255,255,.72); text-decoration: none; min-height: 42px; display: flex; align-items: center; padding: 0 12px; border-radius: 8px; font-weight: 800; }
.sf-nav__link[aria-current="page"] { background: rgba(255,255,255,.12); color: #fff; }
.sf-main { min-width: 0; }
.sf-topbar { min-height: 64px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 22px; border-bottom: 1px solid var(--sf-line); background: rgba(244,248,250,.88); backdrop-filter: blur(12px); position: sticky; top: 0; z-index: 20; }
[data-theme="dark"] .sf-topbar { background: rgba(7,22,29,.86); }
.sf-mobile-brand { display: none; font-weight: 900; }
.sf-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sf-page { max-width: 1180px; margin: 0 auto; padding: 22px; }
.sf-page-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin-bottom: 18px; }
.sf-eyebrow { color: var(--sf-river); font-size: 12px; font-weight: 900; margin-bottom: 5px; }
.sf-page-title { margin: 0; font-size: 24px; line-height: 1.18; }
.sf-page-sub { margin: 6px 0 0; color: var(--sf-muted); font-size: 14px; }
.sf-panel, .sf-metric, .sf-card { background: var(--sf-surface); border: 1px solid var(--sf-line); border-radius: 10px; box-shadow: var(--sf-shadow); }
.sf-panel { padding: 16px; }
.sf-section-title { margin: 0 0 12px; font-size: 15px; font-weight: 900; color: var(--sf-ink); }
.sf-card-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.sf-metric { padding: 14px; min-height: 96px; }
.sf-metric__label { color: var(--sf-muted); font-size: 12px; font-weight: 800; }
.sf-metric__value { margin-top: 8px; font-size: 26px; font-weight: 950; line-height: 1; }
.sf-metric__note { margin-top: 8px; color: var(--sf-muted); font-size: 12px; }
.sf-btn { min-height: 40px; border: 1px solid var(--sf-line); border-radius: 8px; padding: 0 13px; background: var(--sf-surface); color: var(--sf-ink); font-weight: 850; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
.sf-btn--primary { background: var(--sf-river); border-color: var(--sf-river); color: #fff; }
.sf-btn--ghost { background: var(--sf-field); }
.sf-btn--danger { border-color: var(--sf-red); color: var(--sf-red); background: transparent; }
.sf-icon-btn { width: 40px; min-width: 40px; padding: 0; }
.sf-status { display: inline-flex; align-items: center; min-height: 24px; padding: 0 8px; border-radius: 6px; font-size: 12px; font-weight: 900; border: 1px solid transparent; }
.sf-status--ok { color: var(--sf-green); background: rgba(22,138,91,.1); border-color: rgba(22,138,91,.25); }
.sf-status--pending { color: #8a5d00; background: rgba(244,183,64,.18); border-color: rgba(244,183,64,.45); }
.sf-status--full, .sf-status--danger { color: var(--sf-red); background: rgba(217,74,58,.1); border-color: rgba(217,74,58,.28); }
.sf-status--muted { color: var(--sf-muted); background: var(--sf-field); border-color: var(--sf-line); }
.sf-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.sf-field { display: grid; gap: 4px; }
.sf-field label { color: var(--sf-muted); font-size: 12px; font-weight: 850; }
.sf-field input, .sf-field select, .sf-field textarea { width: 100%; min-height: 40px; border: 1px solid var(--sf-line); border-radius: 8px; background: var(--sf-field); color: var(--sf-ink); padding: 8px 10px; }
.sf-field--full { grid-column: 1 / -1; }
.sf-empty { border: 1px dashed var(--sf-line); border-radius: 10px; padding: 24px; text-align: center; color: var(--sf-muted); background: var(--sf-surface); }
.sf-modal-bg { position: fixed; inset: 0; display: none; align-items: center; justify-content: center; padding: 18px; background: rgba(0,0,0,.5); z-index: 100; }
.sf-modal-bg.show { display: flex; }
.sf-modal { width: min(680px, 100%); max-height: 88vh; display: flex; flex-direction: column; overflow: hidden; background: var(--sf-surface); border-radius: 12px; border: 1px solid var(--sf-line); }
.sf-modal__head { padding: 16px 18px; border-bottom: 1px solid var(--sf-line); display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.sf-modal__body { padding: 16px 18px; overflow: auto; }

@media (max-width: 820px) {
  .sf-app { display: block; }
  .sf-sidebar { position: static; height: auto; padding: 12px; }
  .sf-brand { display: none; }
  .sf-nav { display: flex; margin-top: 0; overflow-x: auto; gap: 6px; }
  .sf-nav__link { flex: 1; justify-content: center; min-width: 68px; min-height: 40px; padding: 0 10px; }
  .sf-mobile-brand { display: block; }
  .sf-topbar { top: 0; padding: 10px 12px; min-height: 58px; }
  .sf-page { padding: 14px 12px 22px; }
  .sf-page-head { align-items: flex-start; flex-direction: column; }
  .sf-card-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 480px) {
  .sf-card-grid, .sf-form-grid { grid-template-columns: 1fr; }
  .sf-actions { width: 100%; }
  .sf-actions .sf-btn:not(.sf-icon-btn) { flex: 1; }
  .sf-page-title { font-size: 21px; }
}
```

- [ ] **Step 4: Create shared JavaScript**

Create `static/admin/surf-admin.js`:

```javascript
(function(){
  function qs(id){ return document.getElementById(id); }
  function esc(value){
    return String(value || '')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;');
  }
  function won(value){
    return (Number(value) || 0).toLocaleString('ko-KR') + '원';
  }
  function fmtDateTime(value){
    if(!value) return '-';
    const d = new Date(value);
    return d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  }
  function todayLabel(){
    const d = new Date();
    return d.toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'short'});
  }
  function applyTheme(theme){
    const dark = theme === 'dark';
    document.documentElement.toggleAttribute('data-theme', dark);
    const btn = qs('themebtn') || qs('tbtn');
    if(btn) btn.textContent = dark ? '밝게' : '어둡게';
  }
  function toggleTheme(){
    const cur = document.documentElement.hasAttribute('data-theme') ? 'dark' : 'light';
    const next = cur === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('dash_theme', next); } catch(e) {}
    applyTheme(next);
    return next;
  }
  function initTheme(buttonId){
    let theme = 'light';
    try { theme = localStorage.getItem('dash_theme') || 'light'; } catch(e) {}
    applyTheme(theme);
    const btn = buttonId ? qs(buttonId) : (qs('themebtn') || qs('tbtn'));
    if(btn) btn.addEventListener('click', function(){ toggleTheme(); });
  }
  window.SurfAdmin = { qs, esc, won, fmtDateTime, todayLabel, applyTheme, toggleTheme, initTheme };
})();
```

- [ ] **Step 5: Run asset tests**

Run: `pytest tests/test_admin_ui_assets.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add static/admin/surf-admin.css static/admin/surf-admin.js tests/test_admin_ui_assets.py
git commit -m "feat: add surf admin shared assets"
```

---

### Task 2: Login and Shared Shell Adoption

**Files:**
- Modify: `app/routers/admin.py`
- Modify: `app/routers/availability.py`
- Modify: `app/routers/photos.py`
- Modify: `app/routers/dashboard.py`
- Modify: `tests/test_admin_ui_assets.py`

**Interfaces:**
- Consumes: Task 1 `SurfAdmin.initTheme`, `SurfAdmin.toggleTheme`, `surf-admin.css` shell classes.
- Produces: all admin HTML pages reference `/static/admin/surf-admin.css` and `/static/admin/surf-admin.js`; all authenticated pages render nav labels `홈`, `예약`, `사진`, `분석`.

- [ ] **Step 1: Extend failing HTML reference tests**

Append to `tests/test_admin_ui_assets.py`:

```python
import pytest

from app.services import auth


def admin_cookie(monkeypatch):
    monkeypatch.setattr(auth, "verify_session", lambda token: True)
    return {"asess": "test-session"}


@pytest.mark.parametrize("path", ["/admin/", "/availability/admin", "/photos/admin", "/dashboard/"])
def test_authenticated_admin_pages_reference_shared_assets(monkeypatch, path):
    response = client.get(path, cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    assert '<link rel="stylesheet" href="/static/admin/surf-admin.css">' in response.text
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
    assert "/static/admin/surf-admin.css" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_admin_ui_assets.py -v`

Expected: shared asset reference tests fail because pages still use inline duplicated CSS only.

- [ ] **Step 3: Replace login HTML style in `app/routers/admin.py`**

Modify `LOGIN_HTML` so the `<head>` includes:

```html
<link rel="stylesheet" href="/static/admin/surf-admin.css">
```

Use a compact login body that reuses tokens:

```html
<body class="sf-login">
<main class="sf-login-card">
  <div class="sf-login-brand">
    <div class="sf-brand">서퍼스트<small>운영 콘솔</small></div>
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
```

Add login-specific CSS to `surf-admin.css`:

```css
.sf-login { min-height: 100svh; display: grid; place-items: center; padding: 24px; background: var(--sf-navy); }
.sf-login-card { width: min(380px, 100%); background: var(--sf-surface); border: 1px solid var(--sf-line); border-radius: 12px; padding: 28px; box-shadow: 0 24px 70px rgba(0,0,0,.32); }
.sf-login-brand { margin-bottom: 22px; }
.sf-login .sf-brand { color: var(--sf-ink); }
.sf-login .sf-brand small { color: var(--sf-muted); }
.sf-login-form { display: grid; gap: 14px; }
.sf-check { display: flex; align-items: center; gap: 9px; color: var(--sf-muted); font-weight: 750; font-size: 14px; }
.error { background: rgba(217,74,58,.1); border: 1px solid rgba(217,74,58,.28); color: var(--sf-red); border-radius: 8px; padding: 11px 12px; margin-bottom: 14px; }
```

- [ ] **Step 4: Add shell helper markup manually to each authenticated HTML**

In each authenticated page string, include these head references:

```html
<link rel="stylesheet" href="/static/admin/surf-admin.css">
<script src="/static/admin/surf-admin.js"></script>
```

Use this shell pattern with the correct active link:

```html
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
        <a class="sf-btn sf-btn--ghost" href="/admin/logout">로그아웃</a>
      </div>
    </header>
    <main class="sf-page">
      PAGE_CONTENT
    </main>
  </div>
</div>
<script>SurfAdmin.initTheme('themebtn');</script>
```

For `/availability/admin`, set `aria-current="page"` on `예약`.
For `/photos/admin`, set it on `사진`.
For `/dashboard/`, set it on `분석`.

- [ ] **Step 5: Remove conflicting duplicated base styles gradually**

In each page, remove or override old duplicated rules for `body`, `header`, `nav`, `.themebtn`, `.logoutbtn`, `.card`, and old color tokens when they conflict with `surf-admin.css`. Keep page-specific classes for charts, reservation rows, photo album rows, and conversation bubbles until their task rewrites them.

- [ ] **Step 6: Run shell tests**

Run: `pytest tests/test_admin_ui_assets.py -v`

Expected: all tests pass.

- [ ] **Step 7: Run auth regression tests**

Run: `pytest tests/test_login_bruteforce.py -v`

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add app/routers/admin.py app/routers/availability.py app/routers/photos.py app/routers/dashboard.py static/admin/surf-admin.css tests/test_admin_ui_assets.py
git commit -m "feat: apply surf admin shell"
```

---

### Task 3: Home Operations Console

**Files:**
- Modify: `app/routers/admin.py`
- Modify: `static/admin/surf-admin.css`
- Modify: `tests/test_admin_ui_assets.py`

**Interfaces:**
- Consumes: Task 2 shared shell, existing admin APIs `api/stats`, `api/intents`, `api/conversations`, `api/reservation-stats`, `api/reservations`.
- Produces: `/admin/` contains `id="today-timeline"`, `id="ops-alerts"`, `id="intents"`, `id="convos"`, `id="s-pending"`, and action links to `/availability/admin`.

- [ ] **Step 1: Add failing home structure test**

Append to `tests/test_admin_ui_assets.py`:

```python
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
```

- [ ] **Step 2: Run targeted test to verify it fails**

Run: `pytest tests/test_admin_ui_assets.py::test_admin_home_has_operations_console_regions -v`

Expected: FAIL because the current home page has no `today-timeline` region.

- [ ] **Step 3: Rewrite `/admin/` page content**

In `DASHBOARD_HTML`, replace the old top-level content under `<main class="sf-page">` with:

```html
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

<div class="sf-card-grid ops-metrics">
  <div class="sf-metric"><div class="sf-metric__label">오늘 방문</div><div class="sf-metric__value" id="s-today-ppl">-</div><div class="sf-metric__note" id="s-today-rev">-</div></div>
  <div class="sf-metric"><div class="sf-metric__label">이번 달 수입</div><div class="sf-metric__value money" id="s-revenue">-</div><div class="sf-metric__note" id="s-month-ppl">-</div></div>
  <div class="sf-metric"><div class="sf-metric__label">입금대기</div><div class="sf-metric__value" id="s-pending">-</div><div class="sf-metric__note" id="s-pending-sub">-</div></div>
  <div class="sf-metric"><div class="sf-metric__label">예약문의</div><div class="sf-metric__value" id="s-intents">-</div><div class="sf-metric__note">최근 의향 고객</div></div>
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
```

- [ ] **Step 4: Update home JavaScript rendering**

Keep existing `loadAll`, `openUser`, edit, memo, delete, and modal functions. Change metric assignments:

```javascript
document.getElementById('today-label').textContent = SurfAdmin.todayLabel() + ' 기준';
document.getElementById('s-today-ppl').textContent = (resStats.today_people ?? 0) + '명';
document.getElementById('s-today-rev').textContent = SurfAdmin.won(resStats.today_revenue);
document.getElementById('s-revenue').textContent = SurfAdmin.won(resStats.month_revenue);
document.getElementById('s-month-ppl').textContent = '이번 달 ' + (resStats.month_people ?? 0) + '명';
document.getElementById('s-pending').textContent = (resStats.pending_total ?? 0) + '건';
document.getElementById('s-pending-sub').textContent = (resStats.pending_people ?? 0) + '명 · ' + SurfAdmin.won(resStats.pending_amount);
document.getElementById('s-intents').textContent = (intents || []).length + '건';
```

Render `ops-alerts`:

```javascript
const alerts = [];
if((resStats.pending_total ?? 0) > 0) alerts.push(`<a class="ops-alert ops-alert--pending" href="/availability/admin"><b>입금대기 ${resStats.pending_total}건</b><span>${SurfAdmin.won(resStats.pending_amount)} 확인 필요</span></a>`);
if((intents || []).length > 0) alerts.push(`<button class="ops-alert" type="button" onclick="openCard('intents')"><b>예약문의 ${intents.length}건</b><span>최근 문의를 확인하세요</span></button>`);
document.getElementById('ops-alerts').innerHTML = alerts.length ? alerts.join('') : '<div class="sf-empty">지금 처리할 항목이 없습니다.</div>';
```

Render `today-timeline` from `resList` filtered by `slot_date === today`:

```javascript
const today = new Date().toISOString().slice(0,10);
const todayRows = (resList || []).filter(r => r.slot_date === today).sort((a,b) => String(a.time_slot || '').localeCompare(String(b.time_slot || '')));
document.getElementById('today-timeline').innerHTML = todayRows.length ? todayRows.map(r => {
  const status = r.status || '예약';
  const cls = status === '입금대기' ? 'sf-status--pending' : status === '노쇼' ? 'sf-status--danger' : 'sf-status--ok';
  return `<div class="timeline-row">
    <div class="timeline-time">${SurfAdmin.esc(r.time_slot || '-')}</div>
    <div class="timeline-main"><b>${SurfAdmin.esc(r.customer_name || '(이름없음)')}</b><span>${SurfAdmin.esc(r.program || '기타')} · ${Number(r.people)||0}명</span></div>
    <span class="sf-status ${cls}">${SurfAdmin.esc(status)}</span>
  </div>`;
}).join('') : '<div class="sf-empty">오늘 입력된 예약이 없습니다.</div>';
```

- [ ] **Step 5: Add home-specific CSS**

Add to `surf-admin.css`:

```css
.ops-layout { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, .9fr); gap: 12px; margin-top: 14px; }
.ops-layout > section:nth-child(3), .ops-layout > section:nth-child(4) { min-height: 260px; }
.ops-alerts { display: grid; gap: 8px; }
.ops-alert { width: 100%; text-align: left; border: 1px solid var(--sf-line); border-radius: 8px; background: var(--sf-surface-raised); color: var(--sf-ink); padding: 12px; display: flex; justify-content: space-between; gap: 10px; text-decoration: none; cursor: pointer; }
.ops-alert b { display: block; }
.ops-alert span { color: var(--sf-muted); font-size: 13px; }
.ops-alert--pending { border-color: rgba(244,183,64,.55); background: rgba(244,183,64,.12); }
.timeline-list { display: grid; gap: 8px; }
.timeline-row { display: grid; grid-template-columns: 58px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--sf-line); }
.timeline-row:last-child { border-bottom: 0; }
.timeline-time { color: var(--sf-river); font-weight: 950; }
.timeline-main { min-width: 0; }
.timeline-main b, .timeline-main span { display: block; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.timeline-main span { color: var(--sf-muted); font-size: 13px; margin-top: 2px; }
@media (max-width: 920px) { .ops-layout { grid-template-columns: 1fr; } }
```

- [ ] **Step 6: Run home test**

Run: `pytest tests/test_admin_ui_assets.py::test_admin_home_has_operations_console_regions -v`

Expected: PASS.

- [ ] **Step 7: Run admin-related tests**

Run: `pytest tests/test_admin_ui_assets.py tests/test_login_bruteforce.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/routers/admin.py static/admin/surf-admin.css tests/test_admin_ui_assets.py
git commit -m "feat: redesign surf admin home"
```

---

### Task 4: Reservation Workbench

**Files:**
- Modify: `app/routers/availability.py`
- Modify: `static/admin/surf-admin.css`
- Modify: `tests/test_admin_ui_assets.py`

**Interfaces:**
- Consumes: shared shell and existing reservation endpoints under `/availability/api`.
- Produces: `/availability/admin` contains `id="reservation-workbench"`, `id="summary"`, `id="list"`, `id="quick-add-panel"`, and visible status labels `여유`, `주의`, `마감`, `입금대기`.

- [ ] **Step 1: Add failing reservation structure test**

Append to `tests/test_admin_ui_assets.py`:

```python
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
```

- [ ] **Step 2: Run targeted test to verify it fails**

Run: `pytest tests/test_admin_ui_assets.py::test_availability_page_has_workbench_regions -v`

Expected: FAIL because the current page has no `reservation-workbench` marker.

- [ ] **Step 3: Reshape reservation page HTML**

Inside the shared shell main, use:

```html
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
      <section class="sf-panel">
        <div class="panel-headline"><h2 class="sf-section-title">잔여석</h2><span class="sf-page-sub">여유 · 주의 · 마감</span></div>
        <div class="seatlegend">...</div>
        <div class="seat-board" id="summary"></div>
      </section>
      <section class="sf-panel">
        <h2 class="sf-section-title">예약 타임라인</h2>
        <div id="list"></div>
      </section>
    </div>
    <aside class="sf-panel quick-add-panel" id="quick-add-panel">
      <h2 class="sf-section-title">예약 추가</h2>
      EXISTING_FORM_FIELDS
    </aside>
  </div>
</div>
```

Keep all existing form IDs (`f_prog`, `f_time`, `f_time_txt`, `f_name`, `f_people`, `f_plat`, `f_pay`, `f_amount`, `f_deposit`, `f_status`, `f_memo`) so current JavaScript continues to work.

- [ ] **Step 4: Update `renderSummary` status labels**

Change each seat card output to include a status label:

```javascript
const label = s.is_full ? '마감' : (s.remaining <= Math.max(1, Math.ceil(s.capacity * 0.25)) ? '주의' : '여유');
const labelClass = s.is_full ? 'sf-status--full' : (label === '주의' ? 'sf-status--pending' : 'sf-status--ok');
return `<button class="seat-card ${seatClass(s)} grp-${progGroup(s.program)} ${cls}" onclick="openSeat(${i})" type="button">
  <div class="seat-card__top"><span>${esc(s.program)}</span><span class="sf-status ${labelClass}">${label}</span></div>
  <div class="seat-card__time">${esc(s.time_slot)}</div>
  <div class="seat-card__big">${big}</div>
  <div class="seat-card__meta">${s.booked}/${s.capacity}명${s.booked>0?' · 명단 보기':''}</div>
</button>`;
```

- [ ] **Step 5: Update `renderList` row labels**

Keep existing status actions. Change visible row status badge HTML:

```javascript
if(isNo) badge = '<span class="sf-status sf-status--danger">노쇼</span>';
else if(isPend) badge = '<span class="sf-status sf-status--pending">입금대기</span>';
else badge = '<span class="sf-status sf-status--ok">예약</span>';
```

Ensure the confirm button for pending rows keeps text `확정`.

- [ ] **Step 6: Add reservation-specific CSS**

Add to `surf-admin.css`:

```css
.date-workbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.date-workbar input[type="date"] { min-height: 40px; border: 1px solid var(--sf-line); border-radius: 8px; background: var(--sf-field); color: var(--sf-ink); padding: 0 10px; }
.reservation-layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 12px; align-items: start; }
.reservation-main { display: grid; gap: 12px; min-width: 0; }
.quick-add-panel { position: sticky; top: 78px; }
.panel-headline { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; margin-bottom: 10px; }
.seat-board { display: grid; grid-template-columns: repeat(auto-fill, minmax(138px, 1fr)); gap: 8px; }
.seat-card { text-align: left; border: 1px solid var(--sf-line); border-radius: 10px; background: var(--sf-surface-raised); color: var(--sf-ink); padding: 10px; min-height: 116px; cursor: pointer; }
.seat-card__top { display: flex; justify-content: space-between; align-items: center; gap: 6px; font-size: 12px; font-weight: 900; color: var(--sf-muted); }
.seat-card__time { margin-top: 8px; font-weight: 850; }
.seat-card__big { margin-top: 6px; font-size: 25px; line-height: 1; font-weight: 950; }
.seat-card__meta { margin-top: 6px; font-size: 12px; color: var(--sf-muted); }
.res-row { border-bottom: 1px solid var(--sf-line); }
.res-main { display: grid; grid-template-columns: 64px 130px minmax(0, 1fr) 112px 120px; gap: 10px; align-items: center; padding: 11px 0; }
@media (max-width: 980px) {
  .reservation-layout { grid-template-columns: 1fr; }
  .quick-add-panel { position: static; }
}
@media (max-width: 640px) {
  .date-workbar { flex-wrap: wrap; }
  .date-workbar input[type="date"] { flex: 1; min-width: 160px; }
  .seat-board { display: flex; overflow-x: auto; padding-bottom: 4px; }
  .seat-card { min-width: 132px; }
  .res-main { grid-template-columns: 54px minmax(0, 1fr) 76px; }
  .r-prog, .r-amt { display: none; }
}
```

- [ ] **Step 7: Run reservation UI and behavior tests**

Run:

```bash
pytest tests/test_admin_ui_assets.py::test_availability_page_has_workbench_regions tests/test_availability_status.py tests/test_availability_text.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/routers/availability.py static/admin/surf-admin.css tests/test_admin_ui_assets.py
git commit -m "feat: redesign surf reservation workbench"
```

---

### Task 5: Photos and Analytics Pages

**Files:**
- Modify: `app/routers/photos.py`
- Modify: `app/routers/dashboard.py`
- Modify: `static/admin/surf-admin.css`
- Modify: `tests/test_admin_ui_assets.py`

**Interfaces:**
- Consumes: shared shell, existing photo APIs, existing analytics API.
- Produces: photo page contains `id="photo-delivery"` and upload status region; dashboard contains `id="analytics-report"` and keeps tab IDs `p-ov`, `p-ch`, `p-cal`.

- [ ] **Step 1: Add failing page structure tests**

Append to `tests/test_admin_ui_assets.py`:

```python
def test_photos_page_has_delivery_regions(monkeypatch):
    response = client.get("/photos/admin", cookies=admin_cookie(monkeypatch))
    assert response.status_code == 200
    for marker in [
        'id="photo-delivery"',
        'id="album-create-panel"',
        'id="list"',
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
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run:

```bash
pytest tests/test_admin_ui_assets.py::test_photos_page_has_delivery_regions tests/test_admin_ui_assets.py::test_dashboard_page_has_report_regions -v
```

Expected: FAIL because the marker IDs are absent.

- [ ] **Step 3: Reshape photos page content**

In `app/routers/photos.py`, inside shared shell main:

```html
<div id="photo-delivery">
  <div class="sf-page-head">
    <div>
      <div class="sf-eyebrow">사진 전달</div>
      <h1 class="sf-page-title">현장 앨범</h1>
      <p class="sf-page-sub">앨범을 만들고 QR을 손님에게 보여주세요.</p>
    </div>
  </div>
  <section class="sf-panel album-create-panel" id="album-create-panel">
    <div class="sf-form-grid">
      <div class="sf-field sf-field--full">
        <label for="memo">앨범 메모</label>
        <input id="memo" placeholder="예: 8월 23일 오후 강습">
      </div>
      <button class="sf-btn sf-btn--primary" onclick="createAlbum()" type="button">새 앨범 만들기</button>
    </div>
  </section>
  <section class="album-list" id="list"><div class="sf-empty">불러오는 중...</div></section>
</div>
```

- [ ] **Step 4: Update photo album rendering**

In `load()`, render each album with:

```javascript
<article class="album-card ${a.expired?'is-expired':''}" id="album-${a.code}">
  <img class="album-card__qr" src="qr/${a.code}.png" alt="${esc(a.code)} QR">
  <div class="album-card__body">
    <div class="album-card__head">
      <div><div class="album-code">${esc(a.code)}</div><div class="album-meta">${esc(a.memo)||'(메모 없음)'} · 사진 ${a.photo_count||0}장 · ${a.expired?'만료됨':'~'+fmt(a.expires_at)}</div></div>
      <button class="sf-btn sf-btn--danger" onclick="deleteAlbum('${a.code}')" type="button">삭제</button>
    </div>
    <a class="album-link" href="${base}/photos/p/${a.code}" target="_blank">${base}/photos/p/${a.code}</a>
    <div class="album-upload-status" id="upload-status-${a.code}" aria-live="polite"></div>
    <div class="drop" data-code="${a.code}">사진을 끌어다 놓거나 클릭해서 선택</div>
    <input type="file" data-code="${a.code}" multiple accept="image/*" style="display:none">
    <div id="thumbs-${a.code}"></div>
  </div>
</article>
```

In `uploadFiles(code, files)`, set:

```javascript
const status = document.getElementById(`upload-status-${code}`);
if(status) status.textContent = files.length + '장 업로드 중...';
```

On success:

```javascript
if(status) status.textContent = '업로드 완료';
```

On failure:

```javascript
if(status) status.textContent = '업로드 실패. 다시 시도해 주세요.';
```

- [ ] **Step 5: Reshape dashboard page content**

In `app/routers/dashboard.py`, wrap existing analytics tabs with:

```html
<div id="analytics-report">
  <div class="sf-page-head">
    <div>
      <div class="sf-eyebrow">분석</div>
      <h1 class="sf-page-title">영업 리포트</h1>
      <p class="sf-page-sub">매출, 채널, 종목, 요일별 흐름을 확인합니다.</p>
    </div>
    <div class="sf-actions">
      <button class="sf-btn sf-btn--ghost" onclick="reload()" type="button">새로고침</button>
    </div>
  </div>
  EXISTING_TABS_AND_PANELS
</div>
```

Convert `.tabs` buttons to shared-ish report tabs:

```html
<div class="report-tabs">
  <button class="report-tab on" data-tab="ov" onclick="sw('ov')">개요</button>
  <button class="report-tab" data-tab="ch" onclick="sw('ch')">채널·종목</button>
  <button class="report-tab" data-tab="cal" onclick="sw('cal')">캘린더</button>
</div>
```

Update `sw(tab)` selectors from `.tab` to `.report-tab`.

- [ ] **Step 6: Add photo and report CSS**

Add to `surf-admin.css`:

```css
.album-create-panel { margin-bottom: 12px; }
.album-list { display: grid; gap: 12px; }
.album-card { display: grid; grid-template-columns: 132px minmax(0, 1fr); gap: 14px; background: var(--sf-surface); border: 1px solid var(--sf-line); border-radius: 10px; padding: 14px; box-shadow: var(--sf-shadow); }
.album-card.is-expired { opacity: .58; }
.album-card__qr { width: 132px; height: 132px; object-fit: contain; background: #fff; border: 1px solid var(--sf-line); border-radius: 8px; padding: 6px; }
.album-card__head { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
.album-code { font-size: 22px; font-weight: 950; letter-spacing: .04em; }
.album-meta, .album-upload-status { color: var(--sf-muted); font-size: 13px; margin-top: 3px; }
.album-link { display: block; margin-top: 10px; color: var(--sf-river); word-break: break-all; font-size: 13px; }
.drop { border: 1.5px dashed var(--sf-line); border-radius: 9px; margin-top: 10px; padding: 16px; text-align: center; color: var(--sf-muted); background: var(--sf-surface-raised); cursor: pointer; }
.drop.over { border-color: var(--sf-river); color: var(--sf-river); }
.report-tabs { display: flex; gap: 6px; margin-bottom: 12px; overflow-x: auto; }
.report-tab { min-height: 40px; border: 1px solid var(--sf-line); border-radius: 8px; background: var(--sf-surface); color: var(--sf-muted); padding: 0 14px; font-weight: 850; cursor: pointer; white-space: nowrap; }
.report-tab.on { background: var(--sf-river); border-color: var(--sf-river); color: #fff; }
.chartbox, .cbox, .cal-wrap { background: var(--sf-surface); border: 1px solid var(--sf-line); border-radius: 10px; box-shadow: var(--sf-shadow); }
@media (max-width: 640px) {
  .album-card { grid-template-columns: 1fr; }
  .album-card__qr { width: 112px; height: 112px; }
}
```

- [ ] **Step 7: Run page structure tests**

Run:

```bash
pytest tests/test_admin_ui_assets.py::test_photos_page_has_delivery_regions tests/test_admin_ui_assets.py::test_dashboard_page_has_report_regions -v
```

Expected: PASS.

- [ ] **Step 8: Run relevant regression tests**

Run:

```bash
pytest tests/test_admin_ui_assets.py tests/test_photo_cleanup.py tests/test_landing.py -v
```

Expected: PASS. `tests/test_landing.py` confirms the OSON landing remains available.

- [ ] **Step 9: Commit**

```bash
git add app/routers/photos.py app/routers/dashboard.py static/admin/surf-admin.css tests/test_admin_ui_assets.py
git commit -m "feat: redesign surf photos and analytics"
```

---

### Task 6: Full Verification and Visual Pass

**Files:**
- Modify: `static/admin/surf-admin.css` only if screenshots reveal overlap, text clipping, or broken responsive behavior.
- Modify: affected router file only if markup defects block verification.

**Interfaces:**
- Consumes: completed Tasks 1-5.
- Produces: verified admin redesign with passing tests and local server URL.

- [ ] **Step 1: Run full automated tests**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Start local server**

Run:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: server starts and logs Uvicorn running at `http://127.0.0.1:8000`.

- [ ] **Step 3: Check authenticated pages manually**

Open these paths in a browser with a valid admin session:

```text
http://127.0.0.1:8000/admin/login
http://127.0.0.1:8000/admin/
http://127.0.0.1:8000/availability/admin
http://127.0.0.1:8000/photos/admin
http://127.0.0.1:8000/dashboard/
```

Expected:
- Login shows `서퍼스트 운영 콘솔`.
- Authenticated pages share the same nav and visual shell.
- No OSON landing visual changes are visible at `/`.
- Mobile width around 360px has no overlapping nav text, action buttons, or metric values.
- Desktop width around 1280px uses sidebar layout.
- Light/dark theme button changes page colors and persists after reload.

- [ ] **Step 4: Exercise critical workflows**

Use existing pages and APIs:

```text
예약 화면: 날짜 변경 -> 잔여석 board changes -> 예약 추가 form remains usable.
예약 화면: 입금대기 row shows `입금대기` label and `확정` action.
홈 화면: reservation intent modal opens from an intent row.
사진 화면: album create button calls `createAlbum()`, album card renders QR and upload zone.
분석 화면: tabs switch between `개요`, `채널·종목`, `캘린더`.
```

Expected: no JavaScript console errors for missing functions or missing element IDs.

- [ ] **Step 5: Fix visual defects found in Step 3 or Step 4**

If text overlaps on mobile, adjust only the relevant CSS selectors. For example:

```css
.sf-metric__value { overflow-wrap: anywhere; }
.sf-btn { white-space: nowrap; }
@media (max-width: 420px) { .sf-actions .sf-btn { min-width: 0; } }
```

Run the relevant targeted test after each fix:

```bash
pytest tests/test_admin_ui_assets.py -v
```

Expected: PASS.

- [ ] **Step 6: Final status check**

Run:

```bash
git status --short
```

Expected: only intentional admin redesign files are modified. Existing unrelated `D start_server.command` may remain if it predates this work; do not stage it unless the user explicitly asks.

- [ ] **Step 7: Commit final polish if changes were made**

If Step 5 changed files:

```bash
git add static/admin/surf-admin.css app/routers/admin.py app/routers/availability.py app/routers/photos.py app/routers/dashboard.py tests/test_admin_ui_assets.py
git commit -m "fix: polish surf admin responsive ui"
```

If Step 5 made no changes, skip this commit.

---

## Self-Review

Spec coverage:
- Shared visual system, dark theme, shell, nav, buttons, status labels, and responsive constraints are covered by Tasks 1-2.
- Login is covered by Task 2.
- Home operations console is covered by Task 3.
- Reservation workbench is covered by Task 4.
- Photos and dashboard are covered by Task 5.
- Verification across tests, local server, mobile, desktop, theme, and workflows is covered by Task 6.
- OSON landing exclusion is covered by Task 1 and Task 5 tests.

Placeholder scan:
- The plan contains no `TBD`, `TODO`, or unspecified implementation steps.

Interface consistency:
- Shared `window.SurfAdmin` functions are defined in Task 1 before later tasks consume them.
- Shared CSS class names used in Tasks 2-5 are defined in Task 1 or extended in the task that first needs them.
