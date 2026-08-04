"""Anthropic API 치명적 오류 감지 + 회로 차단(circuit breaker).

2026-08-02 크레딧 소진 장애(15시간+)에서 얻은 교훈 두 가지를 코드로 박제한다.

1) 재시도가 무의미한 오류를 재시도했다.
   크레딧 소진(400 invalid_request_error)·키 만료(401)·모델 오류(404)는
   몇 초 기다린다고 낫지 않는다. 그런데 get_reply는 오버로드(529)와 구분 없이
   7회(backoff 누적 30초) 재시도했다. 콜백 모드에서 손님은 매 문의마다
   30초를 기다린 뒤 폴백 안내문을 받았다. 15시간 내내.
   → 치명적 오류는 즉시 폴백하고, 회로를 열어 이후 요청은 API를 아예 안 부른다.
     회로 복구는 4분 주기 워밍 루프가 성공하면 자동.

2) 경보는 갔지만 6시간마다 한 번이라 놓쳤다(사장님 해외출장 중).
   → 치명적 오류는 전용 경보로 30분마다, 경과 시간을 명시해 재발송한다.
     "3시간째 전면 장애"는 "실패했습니다"보다 행동을 유발한다.
"""

import time
import logging

from app.services.slack import notify_system_alert

logger = logging.getLogger(__name__)


# 재시도해도 절대 낫지 않는 오류 → 문자열 매칭. anthropic SDK 예외 타입에만
# 의존하지 않는 이유: 크레딧 소진은 401/403이 아니라 400 BadRequest로 오기 때문에
# 타입만으로는 "잘못된 요청"과 구분되지 않는다. 실제 응답 메시지가 유일한 단서다.
_FATAL_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        "credit balance is too low",
        "credit",
        "💳 *크레딧 소진* — console.anthropic.com → Plans & Billing에서 "
        "충전하세요. 자동충전(auto-reload)이 꺼져 있으면 함께 켜주세요.",
    ),
    (
        "invalid x-api-key",
        "auth",
        "🔑 *API 키 무효* — Railway 환경변수 ANTHROPIC_API_KEY를 확인하세요.",
    ),
    (
        "authentication_error",
        "auth",
        "🔑 *인증 실패* — Railway 환경변수 ANTHROPIC_API_KEY를 확인하세요.",
    ),
    (
        "permission_error",
        "auth",
        "🚫 *권한 오류* — API 키 권한/워크스페이스 설정을 확인하세요.",
    ),
    (
        "not_found_error",
        "model",
        "🧩 *모델 ID 오류* — agent.py의 MODEL/FALLBACK_MODEL이 유효한지 확인하세요.",
    ),
)


def classify_fatal(error: BaseException) -> tuple[str, str] | None:
    """치명적(재시도 무의미) 오류면 (종류, 슬랙 힌트), 아니면 None.

    오버로드(529)·rate limit(429)·타임아웃은 일시 오류이므로 None을 반환해
    기존 재시도 경로를 그대로 타게 한다.
    """
    text = str(error).lower()
    for pattern, kind, hint in _FATAL_PATTERNS:
        if pattern in text:
            return kind, hint
    return None


class ApiCircuit:
    """치명적 오류 동안 Anthropic 호출을 차단하는 회로.

    열림(open) = API가 확실히 죽은 상태. get_reply는 호출을 건너뛰고 즉시
    정적 폴백으로 답한다(손님 대기시간 30초 → 0초).
    닫힘 복구는 워밍 루프(4분 주기)의 성공이 유일한 신호다. 요청 경로에서
    재시도로 복구를 탐지하지 않는다 — 그러면 다시 손님이 대기하게 되므로.
    """

    def __init__(self, realert_sec: float = 1800.0):
        self.realert_sec = realert_sec
        self.kind: str | None = None
        self.hint: str = ""
        self.opened_at: float = 0.0
        self._last_alert: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.kind is not None

    @property
    def open_duration_sec(self) -> float:
        return time.monotonic() - self.opened_at if self.is_open else 0.0

    async def trip(self, kind: str, hint: str, error: BaseException) -> None:
        """치명적 오류 발생 → 회로를 열고(이미 열려 있으면 유지) 경보를 관리한다."""
        now = time.monotonic()
        first = not self.is_open
        if first:
            self.opened_at = now
        self.kind = kind
        self.hint = hint

        if first or now - self._last_alert >= self.realert_sec:
            self._last_alert = now
            mins = int(self.open_duration_sec // 60)
            elapsed = "방금 발생" if first else f"*{mins}분째 지속 중*"
            await notify_system_alert(
                f"🚨 *카톡 AI 전면 장애 ({elapsed})*\n"
                f"손님 문의에 AI 답변이 나가지 않습니다. 정적 안내문만 발송 중.\n"
                f"{hint}\n"
                f"원문: {str(error)[:300]}"
            )
        logger.error(f"Anthropic 회로 개방({kind}, {int(self.open_duration_sec)}s): {error}")

    async def close(self) -> None:
        """워밍 성공 → 회로 복구."""
        if not self.is_open:
            return
        mins = int(self.open_duration_sec // 60)
        self.kind = None
        self.hint = ""
        self.opened_at = 0.0
        self._last_alert = 0.0
        await notify_system_alert(
            f"🟢 *카톡 AI 복구* — 총 {mins}분간 장애였습니다. 지금은 정상 응답 중입니다."
        )

    def status(self) -> dict:
        """헬스체크/대시보드용 상태 스냅샷."""
        return {
            "open": self.is_open,
            "kind": self.kind,
            "open_minutes": int(self.open_duration_sec // 60),
        }


# 전역 회로 — 워밍 루프와 요청 경로가 같은 인스턴스를 공유한다.
anthropic_circuit = ApiCircuit()
