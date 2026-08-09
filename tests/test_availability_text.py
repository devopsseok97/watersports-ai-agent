import pytest

import app.services.availability as av


@pytest.fixture
def rows(monkeypatch):
    data: list[dict] = []

    async def fake_range(start, end):
        return data

    monkeypatch.setattr(av, "get_reservations_range", fake_range)
    return data


@pytest.mark.anyio
async def test_only_full_slots_are_injected(rows):
    """프롬프트는 이 목록을 "마감된 타임만 표시"로 읽는다.

    여유 있는 슬롯이 섞여 들어가면 모델이 그것도 마감으로 해석해
    예약 가능한 손님에게 "불가"라고 답한다 (예약 유실).
    """
    rows.extend([
        {"slot_date": "2026-08-09", "program": "데이카약",
         "time_slot": "10:00", "people": 2, "status": "예약"},   # 38석 여유
        {"slot_date": "2026-08-09", "program": "윈드서핑",
         "time_slot": "09:00", "people": 5, "status": "예약"},   # 마감
    ])

    text = await av.build_availability_text()

    assert "윈드서핑 09:00" in text
    assert "데이카약" not in text
    assert "자리 남음" not in text


@pytest.mark.anyio
async def test_no_full_slot_means_everything_open(rows):
    rows.append(
        {"slot_date": "2026-08-09", "program": "데이카약",
         "time_slot": "10:00", "people": 2, "status": "예약"}
    )

    text = await av.build_availability_text()

    assert "마감" not in text
