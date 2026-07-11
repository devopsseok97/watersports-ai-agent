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
