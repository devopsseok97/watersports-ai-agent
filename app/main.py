import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import kakao, health, admin, photos, availability
from app.config import settings

_log = logging.getLogger(__name__)
if not getattr(settings, "admin_password", ""):
    _log.warning("⚠️  ADMIN_PASSWORD 미설정: 관리자 대시보드 인증 없이 접근 허용됨 (운영 환경에서는 반드시 설정하세요)")

app = FastAPI(title="WaterSports AI Agent", version="0.3.0")

app.include_router(health.router)
app.include_router(kakao.router, prefix="/kakao")
app.include_router(admin.router, prefix="/admin")
app.include_router(photos.router, prefix="/photos")
app.include_router(availability.router, prefix="/availability")

# 사진 파일 정적 서빙 (photo_storage/{code}/{file} → /media/{code}/{file})
PHOTO_ROOT = Path(__file__).resolve().parents[1] / "photo_storage"
PHOTO_ROOT.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=str(PHOTO_ROOT)), name="media")