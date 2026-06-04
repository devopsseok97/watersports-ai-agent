import httpx
from app.config import settings
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

KMA_BASE_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"

DEFAULT_NX = 68
DEFAULT_NY = 127

BAD_WEATHER_CODES = {
    "PTY": {
        "1": "비가 내리고 있어 오늘은 운영이 어려울 수 있어요 ☔",
        "2": "비/눈이 내리고 있어 오늘은 운영이 어려울 수 있어요 🌨️",
        "3": "눈이 내리고 있어 오늘은 운영이 어려울 수 있어요 ❄️",
        "4": "소나기가 내리고 있어 오늘은 운영이 어려울 수 있어요 🌦️",
    }
}

_cache: dict = {"result": None, "ts": 0}
CACHE_TTL = 300  # 5분


async def get_operation_status(nx: int = DEFAULT_NX, ny: int = DEFAULT_NY) -> str:
    """기상청 API로 현재 날씨 확인 후 운영 가능 여부 반환 (5분 캐싱)"""
    if _cache["result"] and time.time() - _cache["ts"] < CACHE_TTL:
        return _cache["result"]

    # 초단기실황은 매시 40분 이후 생성 → 40분 빼서 직전 시각 조회
    now = datetime.now() - timedelta(minutes=40)
    base_date = now.strftime("%Y%m%d")
    base_time