import time

import pytest

from app.services.agent import AgentService


class _AlwaysFailingMessages:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        raise self.error


@pytest.fixture
def svc():
    service = AgentService()
    fake = _AlwaysFailingMessages(RuntimeError("overloaded_error: 529"))

    class Client:
        messages = fake

    service.client = Client()
    return service, fake


@pytest.mark.anyio
async def test_retry_backoff_never_exceeds_deadline(svc):
    """backoff sleep이 예산을 넘겨서는 안 된다.

    넘기면 동기 모드에서 카톡 5초 타임아웃을 놓쳐 손님에게 아무 답도 안 간다.
    """
    service, _ = svc
    budget = 4.2  # 동기 모드 실제 값 (_safe_reply 기본 timeout_sec)
    started = time.monotonic()
    reply = await service.get_reply(
        user_id="deadline-test",
        message="패들보드 가격 얼마예요?",
        timeout_sec=budget,
    )
    elapsed = time.monotonic() - started

    assert elapsed <= budget + 0.3, f"예산 {budget}s를 {elapsed:.2f}s로 초과"
    assert reply
