"""api_health 회로 차단 테스트.

2026-08-02 크레딧 소진 장애 재발 방지 로직의 회귀 테스트.
슬랙 전송은 전부 monkeypatch로 가로채 실제 웹훅을 때리지 않는다.
"""

import pytest

from app.services import api_health
from app.services.api_health import ApiCircuit, classify_fatal


@pytest.fixture
def sent(monkeypatch):
    """notify_system_alert를 가로채 전송된 메시지를 수집한다."""
    box: list[str] = []

    async def fake_notify(text: str):
        box.append(text)

    monkeypatch.setattr(api_health, "notify_system_alert", fake_notify)
    return box


# ── classify_fatal ────────────────────────────────────────────────────────

def test_크레딧_소진은_치명적으로_분류된다():
    # 2026-08-02 프로덕션 로그의 실제 문구
    err = Exception(
        "Error code: 400 - {'type': 'invalid_request_error', 'message': "
        "'Your credit balance is too low to access the Anthropic API. "
        "Please go to Plans & Billing to upgrade or purchase credits.'}"
    )
    result = classify_fatal(err)
    assert result is not None
    kind, hint = result
    assert kind == "credit"
    assert "Plans & Billing" in hint


def test_인증오류는_치명적으로_분류된다():
    err = Exception("Error code: 401 - {'type': 'authentication_error'}")
    assert classify_fatal(err)[0] == "auth"


def test_모델오류는_치명적으로_분류된다():
    err = Exception("Error code: 404 - {'type': 'not_found_error'}")
    assert classify_fatal(err)[0] == "model"


@pytest.mark.parametrize("msg", [
    "Error code: 529 - {'type': 'overloaded_error'}",
    "Error code: 429 - {'type': 'rate_limit_error'}",
    "Connection error.",
    "Request timed out",
])
def test_일시오류는_치명적이_아니다(msg):
    """오버로드·rate limit은 재시도가 유효하므로 회로를 열면 안 된다."""
    assert classify_fatal(Exception(msg)) is None


# ── ApiCircuit ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_첫_치명적_오류에_회로가_열리고_경보가_간다(sent):
    c = ApiCircuit()
    assert c.is_open is False

    await c.trip("credit", "충전하세요", Exception("credit balance is too low"))

    assert c.is_open is True
    assert c.kind == "credit"
    assert len(sent) == 1
    assert "전면 장애" in sent[0]


@pytest.mark.anyio
async def test_재알림_주기_전에는_경보를_반복하지_않는다(sent):
    """손님 문의가 몰릴 때 회로가 계속 trip돼도 슬랙을 도배하면 안 된다."""
    c = ApiCircuit(realert_sec=1800)
    err = Exception("credit balance is too low")

    for _ in range(50):
        await c.trip("credit", "충전하세요", err)

    assert len(sent) == 1


@pytest.mark.anyio
async def test_재알림_주기가_지나면_경과시간과_함께_다시_알린다(sent):
    c = ApiCircuit(realert_sec=0.0)  # 즉시 재알림
    err = Exception("credit balance is too low")

    await c.trip("credit", "충전하세요", err)
    await c.trip("credit", "충전하세요", err)

    assert len(sent) == 2
    assert "지속 중" in sent[1]


@pytest.mark.anyio
async def test_복구되면_회로가_닫히고_복구알림이_간다(sent):
    c = ApiCircuit()
    await c.trip("credit", "충전하세요", Exception("credit balance is too low"))
    sent.clear()

    await c.close()

    assert c.is_open is False
    assert c.kind is None
    assert len(sent) == 1
    assert "복구" in sent[0]


@pytest.mark.anyio
async def test_열리지_않은_회로를_닫아도_알림이_가지_않는다(sent):
    """정상 상태에서 4분마다 도는 워밍 성공이 슬랙을 도배하면 안 된다."""
    c = ApiCircuit()
    for _ in range(10):
        await c.close()
    assert sent == []


@pytest.mark.anyio
async def test_status_스냅샷(sent):
    c = ApiCircuit()
    assert c.status() == {"open": False, "kind": None, "open_minutes": 0}

    await c.trip("credit", "충전하세요", Exception("credit balance is too low"))
    s = c.status()
    assert s["open"] is True
    assert s["kind"] == "credit"


# ── 요청 경로 통합: 회로가 실제로 손님 대기시간을 없애는가 ──────────────────

class _FakeMessages:
    """create()가 항상 크레딧 소진 오류를 던지는 가짜 클라이언트."""

    def __init__(self):
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        raise Exception(
            "Error code: 400 - {'type': 'invalid_request_error', 'message': "
            "'Your credit balance is too low to access the Anthropic API.'}"
        )


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


@pytest.fixture
def agent(monkeypatch, sent):
    """전역 회로를 매 테스트마다 초기화한 AgentService."""
    from app.services import agent as agent_mod

    monkeypatch.setattr(api_health.anthropic_circuit, "kind", None)
    monkeypatch.setattr(api_health.anthropic_circuit, "opened_at", 0.0)
    monkeypatch.setattr(api_health.anthropic_circuit, "_last_alert", 0.0)
    # 캐시 미충전 상태에서도 프롬프트가 만들어지도록 외부 의존 값을 고정
    monkeypatch.setattr(agent_mod, "get_cached_weather", lambda: "맑음", raising=False)
    monkeypatch.setattr(agent_mod, "get_cached_availability", lambda: "", raising=False)

    svc = agent_mod.AgentService()
    svc.client = _FakeClient()
    return svc


@pytest.mark.anyio
async def test_크레딧_오류는_첫_시도에서_중단된다(agent, sent):
    """핵심 회귀 테스트.

    기존 코드는 크레딧 오류에도 7회(backoff 누적 약 30초) 재시도했다.
    이제 1회 실패로 확정 판단하고 즉시 폴백해야 한다.
    """
    reply = await agent.get_reply("u1", "가격 얼마예요?", timeout_sec=50.0)

    assert agent.client.messages.calls == 1, "치명적 오류인데 재시도가 발생했다"
    assert api_health.anthropic_circuit.is_open is True
    assert reply  # 손님은 빈 응답이 아니라 정적 폴백을 받는다


@pytest.mark.anyio
async def test_회로가_열려있으면_API를_아예_호출하지_않는다(agent, sent):
    """장애가 이미 확정된 뒤 들어온 손님 문의는 대기 0초로 폴백을 받아야 한다."""
    await api_health.anthropic_circuit.trip(
        "credit", "충전하세요", Exception("credit balance is too low")
    )

    reply = await agent.get_reply("u2", "가격 얼마예요?", timeout_sec=50.0)

    assert agent.client.messages.calls == 0
    assert reply
