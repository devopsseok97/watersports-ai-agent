# 오손(OSON) 홍보 랜딩페이지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 Railway FastAPI 앱의 `/`에 오손(OSON) B2B 홍보 랜딩페이지를 서빙하고, 도입 문의 리드를 Supabase + 슬랙으로 수집한다.

**Architecture:** 새 라우터 `app/routers/landing.py`가 `GET /`(정적 HTML)과 `POST /api/leads`(문의 접수)를 담당. 리드는 Supabase `leads` 테이블에 저장하고 기존 슬랙 웹훅으로 알림. HTML은 `static/landing/index.html` 단일 파일(모바일 퍼스트), 힉스필드 디자인 초안을 참고해 스타일링.

**Tech Stack:** FastAPI 0.115, supabase-py 2.7(비동기), httpx(슬랙 웹훅), pytest(신규, dev 전용)

## Global Constraints

- 카톡 응대 최우선: 랜딩 코드는 kakao 라우터와 완전 분리, 공유 상태 없음
- 가격 비공개: 페이지에 금액 표기 금지, "문의 시 안내"로만
- 브랜드명: 오손 (영문 OSON) — 카피에 "오! 손님" 워드플레이 사용
- 모바일 퍼스트 반응형 (375px 기준으로 먼저 설계)
- main 푸시 = Railway 자동 배포 (사용자가 전부 자동 배포 승인함)
- Supabase 프로젝트: watersports-agent (fvxovjsmnzfviwgxmcab), 모든 테이블 RLS + service_role 전용 정책

---

### Task 1: leads 테이블 생성

**Files:**
- Modify: `supabase_schema.sql` (파일 끝에 추가)

**Interfaces:**
- Produces: Supabase `leads` 테이블 — 컬럼 `id, name, phone, business_name, message, created_at`

- [ ] **Step 1: 스키마 파일에 테이블 정의 추가**

`supabase_schema.sql` 끝에 추가:

```sql
-- 오손 랜딩페이지 도입 문의 리드
CREATE TABLE IF NOT EXISTS leads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    business_name TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_only_leads" ON leads
    FOR ALL TO service_role USING (true) WITH CHECK (true);
```

- [ ] **Step 2: Supabase에 마이그레이션 적용**

Supabase MCP `apply_migration` (project_id: `fvxovjsmnzfviwgxmcab`, name: `create_leads_table`)로 위 SQL 실행.

- [ ] **Step 3: 테이블 확인**

Supabase MCP `list_tables`로 `leads` 존재 + RLS enabled 확인.

- [ ] **Step 4: Commit**

```bash
git add supabase_schema.sql
git commit -m "feat: 도입 문의 리드 테이블 추가"
```

---

### Task 2: 리드 접수 백엔드 (services + 라우터 + 테스트)

**Files:**
- Create: `app/routers/landing.py`
- Create: `tests/__init__.py` (빈 파일), `tests/conftest.py`, `tests/test_landing.py`
- Create: `requirements-dev.txt`
- Modify: `app/services/db.py` (끝에 추가), `app/services/slack.py` (끝에 추가), `app/main.py:97-100` (루트 리다이렉트 교체)

**Interfaces:**
- Consumes: Task 1의 `leads` 테이블, 기존 `get_supabase()`, `settings.slack_webhook_url`
- Produces: `POST /api/leads` (JSON `{name, phone, business_name, message?, website?}` → `{"ok": true}`), `async save_lead(name: str, phone: str, business_name: str, message: str = "")`, `async notify_lead(name: str, phone: str, business_name: str, message: str = "")`. `GET /`는 Task 3의 `static/landing/index.html`을 서빙(파일은 Task 3에서 생성).

- [ ] **Step 1: pytest 의존성 추가**

`requirements-dev.txt` 생성:

```
pytest==8.3.2
```

설치: `venv/bin/pip install -r requirements-dev.txt`

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/__init__.py`: 빈 파일.

`tests/conftest.py`:

```python
import os

# app.config가 요구하는 필수 env를 더미로 채움 (실제 .env보다 우선)
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")
os.environ.setdefault("KMA_API_KEY", "test")
os.environ.setdefault("SLACK_WEBHOOK_URL", "http://localhost/slack")
```

`tests/test_landing.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.landing as landing


@pytest.fixture
def client(monkeypatch):
    saved, notified = [], []

    async def fake_save_lead(name, phone, business_name, message=""):
        saved.append({"name": name, "phone": phone,
                      "business_name": business_name, "message": message})

    async def fake_notify_lead(name, phone, business_name, message=""):
        notified.append(name)

    monkeypatch.setattr(landing, "save_lead", fake_save_lead)
    monkeypatch.setattr(landing, "notify_lead", fake_notify_lead)
    landing._submissions.clear()

    test_app = FastAPI()
    test_app.include_router(landing.router)
    c = TestClient(test_app)
    c.saved, c.notified = saved, notified
    return c


BODY = {"name": "김사장", "phone": "010-1234-5678", "business_name": "한강카약"}


def test_lead_saved_and_notified(client):
    r = client.post("/api/leads", json=BODY)
    assert r.status_code == 200
    assert client.saved[0]["business_name"] == "한강카약"
    assert client.notified == ["김사장"]


def test_honeypot_silently_ignored(client):
    r = client.post("/api/leads", json={**BODY, "website": "http://spam.com"})
    assert r.status_code == 200  # 봇에게는 성공처럼 보임
    assert client.saved == []


def test_rate_limit_returns_429(client):
    for _ in range(5):
        assert client.post("/api/leads", json=BODY).status_code == 200
    assert client.post("/api/leads", json=BODY).status_code == 429


def test_empty_name_rejected(client):
    r = client.post("/api/leads", json={**BODY, "name": ""})
    assert r.status_code == 422
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `venv/bin/python -m pytest tests/test_landing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.landing'`

- [ ] **Step 4: services 함수 구현**

`app/services/db.py` 끝에 추가:

```python
# ---------- 랜딩페이지 리드 ----------

async def save_lead(name: str, phone: str, business_name: str, message: str = ""):
    """도입 문의 리드를 Supabase에 저장"""
    client = await get_supabase()
    await client.table("leads").insert({
        "name": name,
        "phone": phone,
        "business_name": business_name,
        "message": message,
    }).execute()
```

`app/services/slack.py` 끝에 추가:

```python
async def notify_lead(name: str, phone: str, business_name: str, message: str = ""):
    """랜딩페이지 도입 문의 리드를 슬랙으로 알림."""
    now = datetime.now(KST).strftime("%m/%d %H:%M")
    payload = {
        "blocks": [
            {"type": "header",
             "text": {"type": "plain_text", "text": "🎉 오손 도입 문의 접수!"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*시간:*\n{now}"},
                {"type": "mrkdwn", "text": f"*사업장:*\n{business_name}"},
                {"type": "mrkdwn", "text": f"*이름:*\n{name}"},
                {"type": "mrkdwn", "text": f"*연락처:*\n{phone}"},
            ]},
            *(
                [{"type": "section",
                  "text": {"type": "mrkdwn", "text": f"*문의 내용:*\n>{message}"}}]
                if message else []
            ),
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.slack_webhook_url, json=payload)
            response.raise_for_status()
    except Exception as e:
        logger.warning(f"리드 슬랙 알림 전송 실패: {e}")
```

- [ ] **Step 5: landing 라우터 구현**

`app/routers/landing.py`:

```python
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.db import save_lead
from app.services.slack import notify_lead

router = APIRouter()

_LANDING_HTML = Path(__file__).parent.parent.parent / "static" / "landing" / "index.html"

RATE_LIMIT = 5          # IP당 시간당 최대 제출 수
RATE_WINDOW = 3600      # 초
_submissions: dict[str, deque] = defaultdict(deque)


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    phone: str = Field(min_length=5, max_length=30)
    business_name: str = Field(min_length=1, max_length=100)
    message: str = Field(default="", max_length=2000)
    website: str = ""  # honeypot — 사람 눈에 안 보이는 필드, 채워져 있으면 봇


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    q = _submissions[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


@router.get("/", include_in_schema=False)
async def landing_page():
    return FileResponse(_LANDING_HTML, media_type="text/html")


@router.post("/api/leads")
async def create_lead(lead: LeadIn, request: Request):
    if lead.website:
        return {"ok": True}  # 봇에게 성공으로 응답하고 조용히 버림
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="잠시 후 다시 시도해주세요")
    await save_lead(lead.name, lead.phone, lead.business_name, lead.message)
    await notify_lead(lead.name, lead.phone, lead.business_name, lead.message)
    return {"ok": True}
```

- [ ] **Step 6: main.py 연결**

`app/main.py`에서 기존 루트 핸들러를 landing 라우터로 교체:

```python
# 삭제:
@app.get("/")
async def root():
    return RedirectResponse(url="/admin/")

# include_router 블록에 추가 (health 다음 줄):
app.include_router(landing.router)
```

상단 import에 `landing` 추가 (`from app.routers import ...` 형태가 아니면 기존 import 스타일을 따를 것). `RedirectResponse` import가 다른 곳에서 안 쓰이면 제거.

- [ ] **Step 7: 테스트 통과 확인**

Run: `venv/bin/python -m pytest tests/test_landing.py -v`
Expected: 4 passed

- [ ] **Step 8: 앱 기동 회귀 확인**

Run: `venv/bin/python -c "from app.main import app; print([r.path for r in app.routes])"`
Expected: `/`, `/api/leads`, `/health`, `/admin/...` 등이 모두 목록에 존재

- [ ] **Step 9: Commit**

```bash
git add app/routers/landing.py app/services/db.py app/services/slack.py app/main.py tests/ requirements-dev.txt
git commit -m "feat: 오손 랜딩 리드 접수 API - honeypot + rate limit + 슬랙 알림"
```

---

### Task 3: 랜딩페이지 HTML (힉스필드 초안 → 이식)

**Files:**
- Create: `static/landing/index.html`

**Interfaces:**
- Consumes: Task 2의 `POST /api/leads` (JSON body: `name, phone, business_name, message, website`)
- Produces: `GET /`가 서빙하는 완결된 단일 HTML (외부 의존성 없음, 인라인 CSS/JS)

- [ ] **Step 1: 힉스필드 디자인 초안 생성**

Higgsfield MCP `create_website`로 초안 요청. 브리프:
"오손(OSON) — 수상레저 사업장을 위한 카카오톡 AI 운영 시스템 B2B 랜딩페이지. 히어로('오! 손님 — 사장님 대신 손님을 받는 AI'), 문제 공감 3개(성수기 카톡 폭주/노쇼/강습 중 응대 불가), 기능 5종 카드(카톡 AI 즉답·예약/잔여석·노쇼 방지·날씨 안내·사진앨범), 도입 사례 1개, 문의 폼. 한국어, 모바일 퍼스트, 물/바다 느낌의 시원한 색."

- [ ] **Step 2: 초안에서 디자인 토큰 추출**

초안 결과(스크린샷/코드)에서 색상 팔레트·타이포·히어로 레이아웃·카드 스타일을 추출해 메모. 코드 전체를 가져오지 말고 디자인 결정만 이식 (외부 프레임워크 의존 금지).

- [ ] **Step 3: 자체 완결 index.html 작성**

`static/landing/index.html` — 아래 베이스라인에 Step 2의 디자인 토큰을 적용해 완성 (구조·폼 로직은 그대로 유지):

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>오손 OSON — 사장님 대신 손님을 받는 AI</title>
<meta name="description" content="카카오톡 AI 응대·예약·노쇼 방지를 한 번에. 수상레저 사업장을 위한 운영 시스템 오손.">
<style>
  :root{--navy:#0a2540;--blue:#0ea5e9;--sky:#e0f2fe;--text:#1e293b;--muted:#64748b}
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Apple SD Gothic Neo','Pretendard',sans-serif;color:var(--text);line-height:1.6}
  .wrap{max-width:960px;margin:0 auto;padding:0 20px}
  header{padding:14px 0;border-bottom:1px solid #e2e8f0}
  .logo{font-size:22px;font-weight:800;color:var(--navy)}
  .logo span{color:var(--blue)}
  .hero{background:linear-gradient(160deg,var(--navy),#075985);color:#fff;padding:72px 0;text-align:center}
  .hero h1{font-size:clamp(28px,6vw,44px);line-height:1.3;margin-bottom:16px}
  .hero p{font-size:clamp(15px,3.5vw,18px);opacity:.9;margin-bottom:32px}
  .cta{display:inline-block;background:var(--blue);color:#fff;font-weight:700;font-size:17px;
       padding:14px 36px;border-radius:12px;text-decoration:none;border:none;cursor:pointer}
  section{padding:56px 0}
  h2{font-size:clamp(22px,5vw,30px);color:var(--navy);text-align:center;margin-bottom:32px}
  .cards{display:grid;grid-template-columns:1fr;gap:16px}
  @media(min-width:640px){.cards{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}}
  .card{background:var(--sky);border-radius:16px;padding:24px}
  .card .emoji{font-size:32px;margin-bottom:8px}
  .card h3{font-size:17px;color:var(--navy);margin-bottom:6px}
  .card p{font-size:14px;color:var(--muted)}
  .case{background:#f8fafc;text-align:center}
  .case blockquote{font-size:17px;max-width:560px;margin:0 auto}
  form{max-width:480px;margin:0 auto;display:flex;flex-direction:column;gap:12px}
  label{font-size:14px;font-weight:600}
  input,textarea{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:10px;font-size:16px}
  .hp{position:absolute;left:-9999px;opacity:0;height:0;overflow:hidden}
  #form-done{text-align:center;font-size:17px;color:var(--navy);font-weight:700}
  footer{padding:32px 0;text-align:center;font-size:13px;color:var(--muted)}
</style>
</head>
<body>
<header><div class="wrap"><div class="logo">오손 <span>OSON</span></div></div></header>

<div class="hero"><div class="wrap">
  <h1>오! 손님 —<br>사장님 대신 손님을 받는 AI</h1>
  <p>카카오톡 문의 응대부터 예약·노쇼 방지까지,<br>강습 중에도 오손이 사장님 대신 일합니다.</p>
  <a class="cta" href="#contact">도입 문의하기</a>
</div></div>

<section><div class="wrap">
  <h2>이런 적 있으시죠?</h2>
  <div class="cards">
    <div class="card"><div class="emoji">📱</div><h3>성수기 카톡 폭주</h3><p>강습 끝나고 보면 문의 수십 개, 답이 늦어 손님을 놓칩니다.</p></div>
    <div class="card"><div class="emoji">🕳️</div><h3>예약해놓고 노쇼</h3><p>자리는 비고, 매출은 사라지고, 확인 전화는 번거롭습니다.</p></div>
    <div class="card"><div class="emoji">🏄</div><h3>강습 중 응대 불가</h3><p>물 위에 있는 동안 전화도 카톡도 받을 수 없습니다.</p></div>
  </div>
</div></section>

<section style="background:#f8fafc"><div class="wrap">
  <h2>오손이 대신합니다</h2>
  <div class="cards">
    <div class="card"><div class="emoji">💬</div><h3>카톡 AI 즉답</h3><p>가격·시간·위치 등 반복 문의에 몇 초 안에 자동 응답.</p></div>
    <div class="card"><div class="emoji">📅</div><h3>예약·잔여석 관리</h3><p>실시간 잔여석 안내와 예약 접수를 대화로 처리.</p></div>
    <div class="card"><div class="emoji">✅</div><h3>노쇼 방지</h3><p>입금 확인·리마인드로 빈자리 손실을 줄입니다.</p></div>
    <div class="card"><div class="emoji">🌤️</div><h3>날씨 안내</h3><p>바람·수온 등 그날 컨디션을 손님에게 자동 안내.</p></div>
    <div class="card"><div class="emoji">📸</div><h3>사진앨범</h3><p>강습 사진을 앨범 링크로 손님에게 바로 전달.</p></div>
  </div>
</div></section>

<section class="case"><div class="wrap">
  <h2>이미 현장에서 일하고 있습니다</h2>
  <blockquote>광나루 서울윈드서핑장 <b>서퍼스트</b>에서 성수기 카카오톡 응대와 예약 관리를 오손이 담당하고 있습니다.</blockquote>
</div></section>

<section id="contact"><div class="wrap">
  <h2>도입 문의</h2>
  <form id="lead-form">
    <div><label for="f-name">이름</label><input id="f-name" name="name" required maxlength="50"></div>
    <div><label for="f-phone">연락처</label><input id="f-phone" name="phone" type="tel" required minlength="5" maxlength="30"></div>
    <div><label for="f-biz">사업장명</label><input id="f-biz" name="business_name" required maxlength="100"></div>
    <div><label for="f-msg">문의 내용 (선택)</label><textarea id="f-msg" name="message" rows="4" maxlength="2000" placeholder="가격은 문의 주시면 안내드려요"></textarea></div>
    <div class="hp"><label>웹사이트<input name="website" tabindex="-1" autocomplete="off"></label></div>
    <button class="cta" type="submit">문의 보내기</button>
  </form>
  <p id="form-done" hidden>접수됐습니다! 하루 안에 연락드릴게요 🙌</p>
</div></section>

<footer><div class="wrap">오손 OSON — 수상레저 사업장을 위한 AI 운영 시스템</div></footer>

<script>
document.getElementById('lead-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  const btn = f.querySelector('button');
  btn.disabled = true;
  try {
    const r = await fetch('/api/leads', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.fromEntries(new FormData(f))),
    });
    if (!r.ok) throw new Error(r.status);
    f.hidden = true;
    document.getElementById('form-done').hidden = false;
  } catch {
    alert('전송에 실패했어요. 잠시 후 다시 시도해주세요.');
    btn.disabled = false;
  }
});
</script>
</body>
</html>
```

- [ ] **Step 4: 로컬 서빙 확인**

Run: `venv/bin/uvicorn app.main:app --port 8000` (백그라운드) 후 `curl -s localhost:8000/ | head -5`
Expected: `<!DOCTYPE html>` 로 시작하는 랜딩 HTML

- [ ] **Step 5: 모바일·데스크톱 뷰 확인**

브라우저에서 `http://localhost:8000/` 열어 375px(모바일)과 데스크톱 폭에서 히어로·카드·폼이 깨지지 않는지 확인. 폼 제출 골든패스도 여기서 1회 실행.

- [ ] **Step 6: Commit**

```bash
git add static/landing/index.html
git commit -m "feat: 오손 홍보 랜딩페이지 - 모바일 퍼스트 단일 HTML"
```

---

### Task 4: 통합 검증 + 배포

**Files:** 없음 (검증만)

- [ ] **Step 1: 전체 테스트**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: 4 passed

- [ ] **Step 2: 실 데이터 경로 검증 (로컬, 실제 .env)**

로컬 서버에 실제 폼 제출 1건:

```bash
curl -s -X POST localhost:8000/api/leads -H 'Content-Type: application/json' \
  -d '{"name":"검증테스트","phone":"010-0000-0000","business_name":"배포전검증"}'
```

Expected: `{"ok":true}` + 슬랙 채널에 "🎉 오손 도입 문의 접수!" 도착.
Supabase MCP `execute_sql`: `SELECT * FROM leads WHERE name='검증테스트';` → 1건 확인 후
`DELETE FROM leads WHERE name='검증테스트';` 로 정리.

- [ ] **Step 3: 기존 라우트 회귀 확인**

```bash
curl -s localhost:8000/health          # {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}" localhost:8000/admin/   # 200 또는 로그인 리다이렉트(3xx)
```

- [ ] **Step 4: 배포 및 프로덕션 확인**

```bash
git push   # Railway 자동 배포
```

배포 완료 후: `curl -s -o /dev/null -w "%{http_code}" https://web-production-9282c.up.railway.app/`
Expected: 200 (랜딩 HTML). `/health`도 200 재확인.
