"""Anthropic 토큰 사용량·비용 계측.

만들게 된 이유 (2026-08-03):
크레딧이 한 달에 두세 번 소진됐는데 "왜 이렇게 많이 쓰지?"에 아무도 답할 수
없었다. 코드 어디에도 response.usage를 기록하는 곳이 없었기 때문이다.
호출은 3군데(get_reply·classify_booking_intent·warm_anthropic_cache)뿐인데도
각각 얼마를 쓰는지 알 수 없으면 최적화도 이상 감지도 불가능하다.

특히 중요한 것: Haiku 4.5의 최소 캐시 가능 길이는 4,096토큰이다. 그보다 짧은
프롬프트에 cache_control을 붙이면 **에러 없이 조용히 무시**되고 전액 정가로
청구된다. 공식 문서가 명시한 유일한 확인 방법이 usage 필드다 —
cache_creation_input_tokens와 cache_read_input_tokens가 둘 다 0이면 캐시 미작동.
이 모듈이 그것을 자동으로 감지해 경고한다.
"""

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# USD per 1M tokens. 출처: platform.claude.com/docs/en/build-with-claude/prompt-caching
# 캐시 쓰기(5m) = 정가 × 1.25 / 캐시 읽기 = 정가 × 0.1
_PRICES: dict[str, dict[str, float]] = {
    # Sonnet 5는 2026-08-31까지 도입가($2/$10), 09-01부터 $3/$15로 인상 예정.
    "claude-sonnet-5":            {"in": 2.0, "write": 2.50, "read": 0.20, "out": 10.0},
    "claude-haiku-4-5-20251001":  {"in": 1.0, "write": 1.25, "read": 0.10, "out": 5.0},
}
_DEFAULT_PRICE = {"in": 1.0, "write": 1.25, "read": 0.10, "out": 5.0}

# 이 길이 미만이면 cache_control이 무시된다 (모델별, 공식 문서 기준)
MIN_CACHEABLE_TOKENS = {
    "claude-haiku-4-5-20251001": 4096,
    "claude-sonnet-5": 1024,
}


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


class UsageTracker:
    """일자별(KST) 토큰·비용 누적. 인메모리이므로 Railway 재시작 시 초기화된다.

    영구 보관이 필요해지면 Supabase에 일 1회 스냅샷을 남기면 되지만,
    지금 목적은 "어디서 새는지" 파악이므로 인메모리로 충분하다.
    """

    def __init__(self, keep_days: int = 7):
        self.keep_days = keep_days
        self.days: dict[str, dict] = {}
        self._cache_miss_warned = False

    def _bucket(self, date: str, model: str, source: str) -> dict:
        day = self.days.setdefault(date, {})
        key = f"{source}|{model}"
        return day.setdefault(key, {
            "calls": 0, "in": 0, "write": 0, "read": 0, "out": 0, "usd": 0.0,
        })

    def record(self, model: str, usage, source: str) -> None:
        """API 응답의 usage를 누적한다. source: reply|intent|warm

        usage가 없거나 형태가 달라도 절대 예외를 던지지 않는다 —
        계측 때문에 손님 응답이 실패하면 본말전도다.
        """
        try:
            n_in    = int(getattr(usage, "input_tokens", 0) or 0)
            n_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
            n_read  = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            n_out   = int(getattr(usage, "output_tokens", 0) or 0)

            p = _PRICES.get(model, _DEFAULT_PRICE)
            usd = (
                n_in    * p["in"]
                + n_write * p["write"]
                + n_read  * p["read"]
                + n_out   * p["out"]
            ) / 1_000_000

            b = self._bucket(_today(), model, source)
            b["calls"] += 1
            b["in"] += n_in
            b["write"] += n_write
            b["read"] += n_read
            b["out"] += n_out
            b["usd"] += usd

            self._detect_cache_failure(model, n_in, n_write, n_read)
            self._prune()
        except Exception as e:  # 계측 실패가 서비스를 죽이면 안 된다
            logger.debug(f"usage 기록 실패(무시): {e}")

    def _detect_cache_failure(self, model: str, n_in: int, n_write: int, n_read: int) -> None:
        """cache_control을 보냈는데 캐시가 0이면 최소 길이 미달이다.

        공식 문서: "Any requests to cache fewer than this number of tokens will be
        processed without caching, and no error is returned." — 즉 로그로만 알 수 있다.
        """
        if n_write or n_read:
            return  # 캐시 정상 작동
        minimum = MIN_CACHEABLE_TOKENS.get(model)
        if not minimum or self._cache_miss_warned:
            return
        self._cache_miss_warned = True
        logger.warning(
            f"⚠️ 프롬프트 캐시 미작동: {model}의 최소 캐시 길이는 {minimum:,}토큰인데 "
            f"이번 요청의 비캐시 입력은 {n_in:,}토큰입니다. cache_control이 무시되어 "
            f"입력 전량이 정가로 청구되고 있습니다(캐시가가 아닌 10배 가격). "
            f"정적 프롬프트를 {minimum:,}토큰 이상으로 늘리거나, 워밍 루프를 제거하세요."
        )

    def _prune(self) -> None:
        if len(self.days) <= self.keep_days:
            return
        for old in sorted(self.days)[:-self.keep_days]:
            self.days.pop(old, None)

    def summary(self) -> dict:
        """ops/대시보드용 요약. 오늘 비용과 용도별 내역."""
        out = {}
        for date in sorted(self.days, reverse=True):
            rows = []
            total = 0.0
            for key, b in sorted(self.days[date].items(),
                                 key=lambda kv: -kv[1]["usd"]):
                source, model = key.split("|", 1)
                total += b["usd"]
                rows.append({
                    "source": source, "model": model, "calls": b["calls"],
                    "input_tokens": b["in"], "cache_write": b["write"],
                    "cache_read": b["read"], "output_tokens": b["out"],
                    "usd": round(b["usd"], 4),
                })
            out[date] = {
                "total_usd": round(total, 4),
                "projected_monthly_usd": round(total * 30, 2),
                "breakdown": rows,
            }
        return out


tracker = UsageTracker()
