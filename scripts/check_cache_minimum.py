"""정적 시스템 프롬프트가 캐시 최소 길이를 넘는지 실측한다.

배경: Haiku 4.5의 최소 캐시 가능 길이는 4,096토큰. 미달이면 cache_control이
**에러 없이 조용히 무시**되고 입력 전량이 정가($1/MTok)로 청구된다.
캐시가($0.10/MTok)의 10배다.

count_tokens 엔드포인트는 **과금되지 않는다**. 마음껏 돌려도 된다.

실행:
    ANTHROPIC_API_KEY=sk-ant-... python scripts/check_cache_minimum.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from app.services.agent import MODEL, build_system_prompt  # noqa: E402
from app.services.usage import MIN_CACHEABLE_TOKENS  # noqa: E402


async def main() -> int:
    static = build_system_prompt()

    # SDK 0.34.0에는 count_tokens가 없으므로 API를 직접 호출한다 (무과금 엔드포인트).
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages/count_tokens",
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "system": [{"type": "text", "text": static}],
                "messages": [{"role": "user", "content": "안녕하세요"}],
            },
        )
    data = resp.json()
    if resp.status_code != 200:
        print(f"❌ count_tokens 실패({resp.status_code}): {data}")
        return 1
    n = data["input_tokens"]
    minimum = MIN_CACHEABLE_TOKENS.get(MODEL, 4096)

    print(f"모델           : {MODEL}")
    print(f"정적 프롬프트  : {len(static):,}자 → {n:,}토큰 (실측)")
    print(f"최소 캐시 길이 : {minimum:,}토큰")

    if n >= minimum:
        print(f"\n✅ 캐시 조건 충족 (여유 {n - minimum:,}토큰)")
        return 0

    short = minimum - n
    # 워밍 360회/일(4분 주기) 기준, Haiku 입력 정가 $1/MTok
    wasted_day = n * 360 / 1_000_000 * 1.0
    print(f"\n❌ {short:,}토큰 부족 — cache_control이 무시되고 있습니다.")
    print(f"   워밍 루프만으로 하루 ${wasted_day:.2f} / 월 ${wasted_day * 30:.2f} 소모 (효과 0)")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
