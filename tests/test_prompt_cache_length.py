"""정적 시스템 프롬프트가 캐시 최소 길이를 유지하는지 지키는 캐너리.

Haiku 4.5의 최소 캐시 가능 길이는 4,096토큰. 미달이면 cache_control이
에러 없이 조용히 무시되고 입력 전량이 정가(캐시가의 10배)로 청구된다.
한국어는 대략 1자 ≈ 0.8~1.5토큰이므로, 6,000자 이상이면 여유 있게 충족.

정확한 실측은 크레딧 충전 후:
    python scripts/check_cache_minimum.py
"""

from app.services.agent import build_system_prompt

# 4,096토큰을 보수적 환산(0.7토큰/자)으로도 넘기는 최소 문자 수
MIN_CHARS = 6000


def test_static_prompt_exceeds_cache_minimum():
    prompt = build_system_prompt()
    assert len(prompt) >= MIN_CHARS, (
        f"정적 프롬프트가 {len(prompt):,}자로 캐시 최소 길이 미달 위험. "
        f"{MIN_CHARS:,}자 미만이면 Haiku 4.5 캐시(4,096토큰)가 무시되어 "
        f"워밍 루프(360회/일)와 모든 응답 입력이 정가로 청구된다."
    )
