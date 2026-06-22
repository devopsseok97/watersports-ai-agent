import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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
            await asyncio.sleep(3600)

    async def _naver_sync_loop():
        from app.services.naver import sync_naver_orders
        await asyncio.sleep(10)  # 서버 기동 후 10초 대기
        while True:
            try:
                n = await sync_naver_orders()
                if n:
                    _log.info(f"네이버 주문 자동 등록: {n}건")
            except Exception as e:
                _log.error(f"네이버 동기화 오류: {e}")
            await asyncio.sleep(60)  # 1분마다

    tasks = [
        asyncio.create_task(_cleanup_loop()),
        asyncio.create_task(_naver_sync_loop()),
    ]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="WaterSports AI Agent", version="0.3.0", lifespan=lifespan)


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/")

app.include_router(health.router)
app.include_router(kakao.router, prefix="/kakao")
app.include_router(admin.router, prefix="/admin")
app.include_router(photos.router, prefix="/photos")
app.include_router(availability.router, prefix="/availability")

_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")