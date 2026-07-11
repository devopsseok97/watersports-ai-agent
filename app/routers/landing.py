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
