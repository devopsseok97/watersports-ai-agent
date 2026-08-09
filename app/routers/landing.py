import logging
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.db import save_lead
from app.services.ratelimit import client_key
from app.services.slack import notify_lead

logger = logging.getLogger(__name__)
router = APIRouter()

_LANDING_HTML = Path(__file__).parent.parent.parent / "static" / "landing" / "index.html"

RATE_LIMIT = 5          # 방문자당 시간당 최대 제출 수
RATE_WINDOW = 3600      # 초
_MAX_TRACKED_IPS = 5000
_submissions: dict[str, deque] = {}


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    phone: str = Field(min_length=5, max_length=30)
    business_name: str = Field(default="", max_length=100)
    message: str = Field(default="", max_length=2000)
    website: str = ""  # honeypot — 사람 눈에 안 보이는 필드, 채워져 있으면 봇


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    q = _submissions.get(key)
    if q is None:
        if len(_submissions) >= _MAX_TRACKED_IPS:
            stale = [k for k, v in _submissions.items()
                     if not v or now - v[-1] > RATE_WINDOW]
            for k in stale:
                _submissions.pop(k, None)
            while len(_submissions) >= _MAX_TRACKED_IPS:
                _submissions.pop(next(iter(_submissions)))
        q = _submissions[key] = deque()
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


@router.get("/", include_in_schema=False)
async def landing_page():
    # no-cache: 재검증 강제 (ETag로 미변경 시 304). 개편 직후 구버전 캐시 노출 방지.
    return FileResponse(_LANDING_HTML, media_type="text/html",
                        headers={"Cache-Control": "no-cache"})


@router.post("/api/leads")
async def create_lead(lead: LeadIn, request: Request):
    if lead.website:
        return {"ok": True}  # 봇에게 성공으로 응답하고 조용히 버림
    if _rate_limited(client_key(request)):
        raise HTTPException(status_code=429, detail="잠시 후 다시 시도해주세요")

    # 저장이 실패해도 알림은 반드시 보낸다. 리드는 오손 영업의 유일한 입구라
    # Supabase 장애 중 들어온 문의를 500으로 튕기면 그런 문의가 있었다는
    # 사실 자체가 사라진다 (손님은 다시 오지 않는다).
    try:
        await save_lead(lead.name, lead.phone, lead.business_name, lead.message)
    except Exception as e:
        logger.error(f"리드 저장 실패 (슬랙 알림은 계속 진행): {e!r}")
    await notify_lead(lead.name, lead.phone, lead.business_name, lead.message)
    return {"ok": True}
