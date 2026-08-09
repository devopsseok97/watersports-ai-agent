"""네이버 동기화 실패가 감시망에 잡히는지 확인.

2026-08-10 발견: 네이버 예약 256건 중 자동 등록 성공은 0건인데 7주 동안
경고가 한 번도 오지 않았다. sync_naver_orders가 토큰 발급 실패·API 오류를
모두 삼키고 0을 반환해, 호출부의 FailureAlarm이 매번 ok()로 처리했기 때문.
실패가 성공으로 집계되면 감시 장치는 있으나 마나다.
"""
import httpx
import pytest

from app.services import naver


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(naver.settings, "naver_client_id", "test-id")
    monkeypatch.setattr(naver.settings, "naver_client_secret", "test-secret")
    naver._processed.clear()
    naver._token_cache.clear()


@pytest.mark.anyio
async def test_token_failure_raises(configured, monkeypatch):
    async def boom():
        raise RuntimeError("토큰 발급 거부")

    monkeypatch.setattr(naver, "_get_token", boom)

    with pytest.raises(Exception):
        await naver.sync_naver_orders()


@pytest.mark.anyio
async def test_order_list_error_raises(configured, monkeypatch):
    async def fake_token():
        return "tok"

    monkeypatch.setattr(naver, "_get_token", fake_token)

    async def handler(request):
        return httpx.Response(401, text="Unauthorized")

    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient

    def patched(*a, **kw):
        kw["transport"] = transport
        return orig(*a, **kw)

    monkeypatch.setattr(naver.httpx, "AsyncClient", patched)

    with pytest.raises(Exception):
        await naver.sync_naver_orders()


@pytest.mark.anyio
async def test_unconfigured_is_not_an_error(monkeypatch):
    """연동을 안 걸어둔 상태는 장애가 아니다 — 알람을 울리면 안 된다."""
    monkeypatch.setattr(naver.settings, "naver_client_id", "")
    assert await naver.sync_naver_orders() == 0
