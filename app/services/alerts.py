import time
import logging

from app.services.slack import notify_system_alert

logger = logging.getLogger(__name__)


class FailureAlarm:
    """외부 의존성 연속 실패 감시 — 임계 도달 시 슬랙 경고, 복구 시 해제 알림.

    2026-07-11 Anthropic 크레딧 소진을 손님이 먼저 발견한 사고 이후,
    모든 백그라운드 루프의 외부 호출에 동일 패턴을 적용한다.
    경고 전송 실패는 삼켜지므로(notify_system_alert) 본 루프를 죽이지 않는다.
    """

    def __init__(self, name: str, threshold: int, hint: str = "",
                 realert_sec: float = 6 * 3600):
        self.name = name
        self.threshold = threshold
        self.hint = hint
        self.realert_sec = realert_sec
        self.fail_count = 0
        self.alerted_at = 0.0

    async def fail(self, error: Exception) -> None:
        self.fail_count += 1
        now = time.monotonic()
        should_alert = self.fail_count == self.threshold or (
            self.fail_count > self.threshold
            and now - self.alerted_at > self.realert_sec
        )
        if should_alert:
            self.alerted_at = now
            msg = (
                f"🔴 *{self.name} 연속 {self.fail_count}회 실패*\n"
                f"오류: {str(error)[:300]}"
            )
            if self.hint:
                msg += f"\n{self.hint}"
            await notify_system_alert(msg)

    async def ok(self) -> None:
        if self.fail_count >= self.threshold:
            await notify_system_alert(f"🟢 *{self.name} 복구* — 다시 정상 동작합니다.")
        self.fail_count = 0
        self.alerted_at = 0.0
