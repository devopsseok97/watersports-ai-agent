import logging

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.routers import kakao, health, admin, photos, availability
from app.config import settings

_log = logging.getLogger(__name__)
if not getattr(settings, "admin_password", ""):
    _log.warning("⚠️  ADMIN_PASSWORD 미설정: 관리자 대시보드 인증 없이 접근 허용됨 (운영 환경에서는 반드시 설정하세요)")

app = FastAPI(title="WaterSports AI Agent", version="0.3.0")


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/")

app.include_router(health.router)
app.include_router(kakao.router, prefix="/kakao")
app.include_router(admin.router, prefix="/admin")
app.include_router(photos.router, prefix="/photos")
app.include_router(availability.router, prefix="/availability")