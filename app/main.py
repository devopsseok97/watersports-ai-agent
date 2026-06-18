import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.routers import kakao, health, admin, photos, availability
from app.config import settings

_log = logging.getLogger(__name__)
if not getattr(settings, "admin_password", ""):
    _log.warning("⚠️  ADMIN_PASSWORD 미설정: 관리자 대시보드 인증 없이 접근 허용됨 (운영 환경에서는 반드시 설정하세요)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def _cleanup_loop():
        from app.routers.photos import cleanup_expired_albums
        while True:
            try:
                deleted = await cleanup_expired_albums()
                if deleted:
                    _log.info(f"만료 앨범 자동 정리: {deleted}개 삭제")
            except Exception as e:
                _log.error(f"만료 앨범 정리 오류: {e}")
            await asyncio.sleep(3600)  # 1시간마다 실행

    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="WaterSports AI Agent", version="0.3.0", lifespan=lifespan)


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/")

app.include_router(health.router)
app.include_router(kakao.router, prefix="/kakao")
app.include_router(admin.router, prefix="/admin")
app.include_router(photos.router, prefix="/photos")
app.include_router(availability.router, prefix="/availability")