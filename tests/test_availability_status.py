import pytest

import app.services.availability as av
import app.services.db as db


class _FakeTable:
    def __init__(self, store):
        self.store = store

    def insert(self, row):
        self.store["inserted"] = row
        return self

    def update(self, patch):
        self.store["updated"] = patch
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a):
        return self

    def gte(self, *a):
        return self

    def lte(self, *a):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a):
        return self

    def range(self, *a):
        return self

    async def execute(self):
        data = self.store.get("data", [{}])

        class R:
            pass

        r = R()
        r.data = data
        return r


class _FakeClient:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _FakeTable(self.store)


@pytest.fixture
def store(monkeypatch):
    store = {}

    async def fake_get_supabase():
        return _FakeClient(store)

    monkeypatch.setattr(av, "get_supabase", fake_get_supabase)
    monkeypatch.setattr(db, "get_supabase", fake_get_supabase)  # select_all이 쓰는 쪽
    return store


# ── 취소 상태 ──────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_set_status_accepts_cancel(store):
    await av.set_reservation_status(1, "취소")
    assert store["updated"]["status"] == "취소"


@pytest.mark.anyio
async def test_set_status_unknown_falls_back_to_reserved(store):
    await av.set_reservation_status(1, "이상한값")
    assert store["updated"]["status"] == "예약"


def test_aggregate_excludes_canceled():
    rows = [
        {"slot_date": "2026-07-15", "program": "데이카약", "time_slot": "10:00", "people": 3, "status": "예약"},
        {"slot_date": "2026-07-15", "program": "데이카약", "time_slot": "10:00", "people": 2, "status": "취소"},
        {"slot_date": "2026-07-15", "program": "데이카약", "time_slot": "10:00", "people": 4, "status": "노쇼"},
    ]
    agg = av.aggregate(rows)
    assert agg[("2026-07-15", "데이카약", "10:00")] == 3


@pytest.mark.anyio
async def test_stats_exclude_canceled(store):
    store["data"] = [
        {"slot_date": "2026-07-15", "people": 2, "amount": 10000, "status": "예약"},
        {"slot_date": "2026-07-15", "people": 1, "amount": 5000, "status": "노쇼"},
        {"slot_date": "2026-07-15", "people": 3, "amount": 30000, "status": "취소"},
    ]
    stats = await av.get_reservation_stats()
    assert stats["total_reservations"] == 1
    assert stats["total_revenue"] == 10000
    # 노쇼율 분모에서 취소 제외: 1/2 = 50%
    assert stats["total_all"] == 2
    assert stats["noshow_rate"] == 50.0
    assert stats["canceled_total"] == 1


# ── 예약 추가 시 상태 선택 ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_add_reservation_with_pending_status(store):
    await av.add_reservation("2026-07-15", "데이카약", status="입금대기")
    assert store["inserted"]["status"] == "입금대기"


@pytest.mark.anyio
async def test_add_reservation_default_status_is_reserved(store):
    await av.add_reservation("2026-07-15", "데이카약")
    assert store["inserted"]["status"] == "예약"


@pytest.mark.anyio
async def test_add_reservation_rejects_invalid_status(store):
    # 추가 폼에서는 예약/입금대기만 선택 가능 — 그 외 값은 예약으로
    await av.add_reservation("2026-07-15", "데이카약", status="취소")
    assert store["inserted"]["status"] == "예약"
