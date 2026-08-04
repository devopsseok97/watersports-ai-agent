"""usage 계측 테스트 — 특히 '캐시 미작동 감지'가 실제로 동작하는지."""

import logging

import pytest

from app.services.usage import UsageTracker, MIN_CACHEABLE_TOKENS


class _Usage:
    def __init__(self, input_tokens=0, cache_creation_input_tokens=0,
                 cache_read_input_tokens=0, output_tokens=0):
        self.input_tokens = input_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.output_tokens = output_tokens


HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"


def test_캐시_미작동을_감지해_경고한다(caplog):
    """핵심 테스트.

    Haiku 4.5 최소 캐시 길이는 4,096토큰. 그보다 짧으면 cache_control이
    조용히 무시되고 전액 정가 청구된다. API는 에러를 내지 않으므로
    usage 필드가 유일한 단서다 — 그걸 우리가 잡아내는지 확인한다.
    """
    t = UsageTracker()
    with caplog.at_level(logging.WARNING):
        # 정적 프롬프트 2,200토큰 → 4,096 미달 → 캐시 생성/읽기 둘 다 0
        t.record(HAIKU, _Usage(input_tokens=2200, output_tokens=300), "reply")

    assert any("캐시 미작동" in r.message for r in caplog.records)


def test_캐시가_작동하면_경고하지_않는다(caplog):
    t = UsageTracker()
    with caplog.at_level(logging.WARNING):
        t.record(HAIKU, _Usage(cache_read_input_tokens=4200,
                               input_tokens=350, output_tokens=300), "reply")
    assert not any("캐시 미작동" in r.message for r in caplog.records)


def test_경고는_한_번만_나간다(caplog):
    """4분마다 도는 워밍이 로그를 도배하면 안 된다."""
    t = UsageTracker()
    with caplog.at_level(logging.WARNING):
        for _ in range(100):
            t.record(HAIKU, _Usage(input_tokens=2200), "warm")
    assert sum("캐시 미작동" in r.message for r in caplog.records) == 1


def test_비용_계산_정확도():
    """Haiku 4.5: 입력 $1/MTok, 출력 $5/MTok, 캐시읽기 $0.10/MTok."""
    t = UsageTracker()
    t.record(HAIKU, _Usage(input_tokens=1_000_000), "reply")
    day = next(iter(t.summary().values()))
    assert day["total_usd"] == pytest.approx(1.0)

    t2 = UsageTracker()
    t2.record(HAIKU, _Usage(output_tokens=1_000_000), "reply")
    assert next(iter(t2.summary().values()))["total_usd"] == pytest.approx(5.0)

    t3 = UsageTracker()
    t3.record(HAIKU, _Usage(cache_read_input_tokens=1_000_000), "reply")
    assert next(iter(t3.summary().values()))["total_usd"] == pytest.approx(0.10)


def test_소넷은_해당_단가로_계산된다():
    """Sonnet 폴백은 Haiku보다 입력 2배·출력 2배 비싸다 — 섞이면 안 된다."""
    t = UsageTracker()
    t.record(SONNET, _Usage(input_tokens=1_000_000), "reply")
    assert next(iter(t.summary().values()))["total_usd"] == pytest.approx(2.0)


def test_용도별로_분리_집계된다():
    """warm이 reply보다 비싸면 배경 루프가 손님 트래픽보다 돈을 더 쓰는 것."""
    t = UsageTracker()
    for _ in range(360):                                   # 하루치 워밍
        t.record(HAIKU, _Usage(input_tokens=2200), "warm")
    for _ in range(50):                                    # 하루치 손님 문의
        t.record(HAIKU, _Usage(input_tokens=2550, output_tokens=400), "reply")

    day = next(iter(t.summary().values()))
    by_source = {r["source"]: r["usd"] for r in day["breakdown"]}
    assert by_source["warm"] == pytest.approx(0.792)
    assert by_source["reply"] == pytest.approx(0.2275)
    assert by_source["warm"] > by_source["reply"] * 3, (
        "워밍 루프가 손님 트래픽의 3배 넘게 쓰고 있다 — 이게 이번 조사의 핵심 발견"
    )


def test_usage가_None이어도_예외가_나지_않는다():
    """계측 실패가 손님 응답을 죽이면 본말전도."""
    t = UsageTracker()
    t.record(HAIKU, None, "reply")
    t.record(HAIKU, object(), "reply")


def test_haiku_최소_캐시_길이는_4096():
    """공식 문서 기준값 — 바뀌면 테스트가 알려준다."""
    assert MIN_CACHEABLE_TOKENS[HAIKU] == 4096
    assert MIN_CACHEABLE_TOKENS[SONNET] == 1024
