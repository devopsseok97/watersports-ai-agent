import pytest

from app.routers.kakao import _ESCALATION_MARKERS
from app.services.agent import FALLBACK_NOTICE, _static_fallback


def _is_escalation(reply: str) -> bool:
    return any(marker in reply for marker in _ESCALATION_MARKERS)


def test_ai_failure_notice_is_escalation():
    """AI 전멸 안내문이 '일반 문의'로 슬랙에 뜨면 사장님이 장애를 놓친다.

    2026-08 회귀: 안내문 문구를 자연화(04b756a)하면서 판정 키워드가 깨져
    오류 폴백이 나가도 🆘 표시가 안 됐다.
    """
    assert _is_escalation(FALLBACK_NOTICE)


@pytest.mark.parametrize("message", ["사진 언제 받을 수 있나요?", "예약 취소하고 싶어요"])
def test_phone_handoff_fallbacks_are_escalation(message):
    reply = _static_fallback(message)
    assert reply is not None
    assert _is_escalation(reply)


def test_price_fallback_is_not_escalation():
    """가격 폴백은 AI 없이도 제대로 답한 것 → 전화 유도가 아니다."""
    reply = _static_fallback("패들보드 얼마예요?")
    assert reply is not None
    assert not _is_escalation(reply)
