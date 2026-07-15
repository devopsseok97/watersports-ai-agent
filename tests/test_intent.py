import pytest

from app.services.agent import AgentService


class _FakeMessages:
    def __init__(self, reply_text=None, error=None):
        self.reply_text = reply_text
        self.error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error

        class Block:
            text = self.reply_text

        class Resp:
            content = [Block()]

        return Resp()


@pytest.fixture
def svc():
    return AgentService()


def _patch(svc, **kwargs):
    fake = _FakeMessages(**kwargs)

    class Client:
        messages = fake

    svc.client = Client()
    return fake


@pytest.mark.anyio
async def test_llm_yes_is_booking(svc):
    _patch(svc, reply_text="Y")
    assert await svc.classify_booking_intent("7월17일 금요일인데 가능한걸까요!") is True


@pytest.mark.anyio
async def test_llm_no_is_not_booking(svc):
    _patch(svc, reply_text="N")
    assert await svc.classify_booking_intent("넵넵! 감사합니다~") is False


@pytest.mark.anyio
async def test_llm_failure_falls_back_to_keywords_positive(svc):
    _patch(svc, error=RuntimeError("api down"))
    assert await svc.classify_booking_intent("패들보드 예약하고 싶어요") is True


@pytest.mark.anyio
async def test_llm_failure_falls_back_to_keywords_negative(svc):
    _patch(svc, error=RuntimeError("api down"))
    assert await svc.classify_booking_intent("안녕하세요!") is False


@pytest.mark.anyio
async def test_unexpected_llm_output_falls_back_to_keywords(svc):
    _patch(svc, reply_text="잘 모르겠어요")
    assert await svc.classify_booking_intent("예약 문의드립니다") is True
