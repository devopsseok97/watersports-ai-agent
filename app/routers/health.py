import httpx
from fastapi import APIRouter

from app.services.api_health import anthropic_circuit

router = APIRouter()


@router.get("/health")
async def health_check():
    """서버 생존 + AI 응답 가능 여부.

    2026-08-02 교훈: 크레딧 소진으로 15시간 넘게 AI가 죽어 있는 동안에도
    이 엔드포인트는 {"status": "ok"}를 반환했다. 프로세스는 살아 있었으니까.
    외부 모니터링이 "ok"만 보고 있으면 제품이 죽어도 아무도 모른다.
    → AI 회로가 열려 있으면 status를 degraded로 낮춘다.

    HTTP 200은 유지한다. 5xx를 내면 Railway가 컨테이너를 재시작하는데,
    크레딧 소진은 재시작으로 해결되지 않고 재시작 루프만 만든다.
    """
    circuit = anthropic_circuit.status()
    if circuit["open"]:
        return {
            "status": "degraded",
            "reason": f"anthropic_{circuit['kind']}",
            "degraded_minutes": circuit["open_minutes"],
            "impact": "카톡 문의에 AI 답변 대신 정적 안내문이 나가는 중",
        }
    return {"status": "ok"}


@router.get("/usage")
async def usage_summary():
    """일자별 토큰·비용 내역 (용도별: reply / intent / warm).

    Anthropic Admin API는 개인 계정에서 못 쓰므로, 서버가 직접 집계한다.
    projected_monthly_usd = 오늘 비용 × 30 (러프한 월 환산).
    breakdown의 cache_write·cache_read가 0이면 프롬프트 캐시가 작동하지 않는 것 —
    입력 토큰이 캐시가(정가의 10%)가 아니라 정가로 청구되고 있다는 뜻이다.
    """
    from app.services.usage import tracker
    return tracker.summary()


@router.get("/ip")
async def get_server_ip():
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get("https://api.ipify.org?format=json")
    return r.json()
