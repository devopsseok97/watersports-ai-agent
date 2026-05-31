import httpx
from app.config import settings
import logging
import time

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
    from datetime import datetime

    if _cache["result"] and time.time() - _cache["ts"] < CACHE_TTL:
        return _cache["result"]

    now = datetime.now()
    base_date = now.strftime("%Y%m%d")
    base_time = now.strftime("%H00")

    params = {
        "serviceKey": settings.kma_api_key,
        "numOfRows": 10,
        "pageNo": 1,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(KMA_BASE_URL, params=params)
            data = response.json()

        items = data["response"]["body"]["items"]["item"]
        for item in items:
            category = item.get("category")
            value = item.get("obsrValue", "0")

            if category == "PTY" and value in BAD_WEATHER_CODES["PTY"]:
                result = BAD_WEATHER_CODES["PTY"][value]
                _cache["result"] = result
                _cache["ts"] = time.time()
                return result

        result = "현재 날씨가 맑아 정상 운영 중입니다 ☀️"
        _cache["result"] = result
        _cache["ts"] = time.time()
        return result

    except Exception as e:
        logger.warning(f"날씨 API 조회 실패: {e}")
        return "운영 중입니다."
