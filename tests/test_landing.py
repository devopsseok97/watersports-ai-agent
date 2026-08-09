import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.landing as landing


@pytest.fixture
def client(monkeypatch):
    saved, notified = [], []

    async def fake_save_lead(name, phone, business_name, message=""):
        saved.append({"name": name, "phone": phone,
                      "business_name": business_name, "message": message})

    async def fake_notify_lead(name, phone, business_name, message=""):
        notified.append(name)

    monkeypatch.setattr(landing, "save_lead", fake_save_lead)
    monkeypatch.setattr(landing, "notify_lead", fake_notify_lead)
    landing._submissions.clear()

    test_app = FastAPI()
    test_app.include_router(landing.router)
    c = TestClient(test_app)
    c.saved, c.notified = saved, notified
    return c


BODY = {"name": "김사장", "phone": "010-1234-5678", "business_name": "한강카약"}


def test_lead_saved_and_notified(client):
    r = client.post("/api/leads", json=BODY)
    assert r.status_code == 200
    assert client.saved[0]["business_name"] == "한강카약"
    assert client.notified == ["김사장"]


def test_honeypot_silently_ignored(client):
    r = client.post("/api/leads", json={**BODY, "website": "http://spam.com"})
    assert r.status_code == 200  # 봇에게는 성공처럼 보임
    assert client.saved == []


def test_rate_limit_returns_429(client):
    for _ in range(5):
        assert client.post("/api/leads", json=BODY).status_code == 200
    assert client.post("/api/leads", json=BODY).status_code == 429


def test_empty_name_rejected(client):
    r = client.post("/api/leads", json={**BODY, "name": ""})
    assert r.status_code == 422


def test_lead_survives_db_failure(client, monkeypatch):
    """DB가 죽어도 리드는 유실되면 안 된다.

    리드는 오손 영업의 유일한 입구다. Supabase 장애 중 들어온 문의가
    500으로 튕기면 손님은 다시 오지 않고, 사장님은 그런 문의가 있었다는
    사실조차 모른다. 최소한 슬랙으로는 연락처가 도착해야 한다.
    """
    async def boom(*a, **kw):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(landing, "save_lead", boom)

    r = client.post("/api/leads", json=BODY)

    assert r.status_code == 200
    assert client.notified == ["김사장"]


def test_rate_limit_is_per_visitor_not_per_proxy(client):
    """레일웨이 엣지 뒤에서는 모든 방문자의 client.host가 프록시 IP로 같다.

    그대로 두면 시간당 리드 5건이 '전체 합산'이 되어, 6번째 방문자부터
    문의 자체가 429로 막힌다 (봇이 아니라 실제 손님이 막힌다).
    """
    for i in range(6):
        r = client.post("/api/leads", json=BODY,
                        headers={"X-Forwarded-For": f"203.0.113.{i}"})
        assert r.status_code == 200, f"{i}번째 방문자가 막힘"

    # 같은 방문자가 계속 보내는 건 여전히 막아야 한다
    for _ in range(4):
        client.post("/api/leads", json=BODY,
                    headers={"X-Forwarded-For": "203.0.113.0"})
    r = client.post("/api/leads", json=BODY,
                    headers={"X-Forwarded-For": "203.0.113.0"})
    assert r.status_code == 429


def test_submission_tracker_is_bounded(client):
    """IP별 기록이 무한히 쌓이면 스캐너 한 번에 메모리가 넘친다."""
    for i in range(landing._MAX_TRACKED_IPS + 50):
        client.post("/api/leads", json=BODY,
                    headers={"X-Forwarded-For": f"198.51.100.{i % 256}.{i}"})
    assert len(landing._submissions) <= landing._MAX_TRACKED_IPS
