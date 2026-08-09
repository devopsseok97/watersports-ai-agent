"""예약 관리 (건별 입력 → 인원 자동 합산).

설계 원칙:
- 사장님이 예약을 '건별'로 입력한다 (이름/인원/플랫폼/시간). 사진 메모장과 동일.
- 종목·시간(슬롯)별 인원은 시스템이 자동 합산 → 잔여좌석/마감 자동 계산.
- customer_name / platform / memo 는 사장님 전용. 챗봇·손님에게 절대 안 나간다.
- 챗봇에는 슬롯별 '잔여 좌석'만 주입한다 (예약자 정보 일절 제외).

정원은 종목별 독립(데카40/데패20 따로).
"""
import logging
import re
from datetime import datetime, timedelta, timezone

from app.services.db import get_supabase

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 종목별 시간대/정원 (agent.py SHOP_CONFIG와 일치)
PROGRAMS = [
    {"key": "데이패들보드", "slots": ["10:00", "13:00", "15:00"], "capacity": 20},
    {"key": "선셋패들보드", "slots": ["18:30"], "capacity": 20},
    {"key": "데이카약", "slots": ["10:00", "13:00", "15:00"], "capacity": 40},
    {"key": "선셋카약", "slots": ["18:30"], "capacity": 40},
    {"key": "윈드서핑", "slots": ["09:00", "13:00"], "capacity": 5},
    {"key": "E포일", "slots": ["09:00", "13:00"], "capacity": 2},
    # 시간 협의 종목: 정해진 슬롯 없음(시간 직접 입력). 정원 관리 대상 아님.
    {"key": "전동e포일", "slots": [], "capacity": None, "note": "시간 협의 후 예약"},
    {"key": "펌핑포일", "slots": [], "capacity": None, "note": "시간 협의 후 예약"},
]

# 종목명 → 정원 빠른 조회
CAPACITY = {p["key"]: p["capacity"] for p in PROGRAMS}

# 예약 플랫폼 (사장님 입력용)
PLATFORMS = ["네이버", "현장", "솜씨당", "탈잉", "클룩"]

# 결제 수단 (사장님 입력용)
PAYMENT_METHODS = ["계좌이체", "현장카드", "현금"]


def today_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def remaining(program: str, booked: int) -> int | None:
    """잔여 좌석. 정원 없는 종목은 None."""
    cap = CAPACITY.get(program)
    if cap is None:
        return None
    return max(cap - booked, 0)


# ────────────────────────────── 예약 건별 CRUD ──────────────────────────────

def _to_amount(amount) -> int:
    """금액 정규화 (콤마/공백/'원' 제거 후 정수). 음수·오류는 0."""
    if amount is None:
        return 0
    try:
        s = str(amount).replace(",", "").replace("원", "").strip()
        return max(int(float(s or 0)), 0)
    except (ValueError, TypeError):
        return 0


async def add_reservation(
    date_str: str,
    program: str,
    time_slot: str = "",
    customer_name: str = "",
    people: int = 1,
    platform: str = "현장",
    memo: str = "",
    amount: int = 0,
    payment_method: str = "계좌이체",
    deposit_amount: int = 0,
    status: str = "예약",
) -> dict:
    """예약 1건 추가. 입금 전 문의는 status='입금대기'로 기록 → 전환율 측정."""
    client = await get_supabase()
    pay = (payment_method or "계좌이체").strip()
    if pay not in PAYMENT_METHODS:
        pay = "계좌이체"
    status = (status or "예약").strip()
    if status not in ("예약", "입금대기"):
        status = "예약"
    row = {
        "status": status,
        "slot_date": date_str,
        "program": program,
        "time_slot": (time_slot or "").strip(),
        "customer_name": (customer_name or "").strip(),
        "people": max(int(people or 1), 1),
        "platform": (platform or "현장").strip(),
        "memo": (memo or "").strip(),
        "amount": _to_amount(amount),
        "payment_method": pay,
        "deposit_amount": _to_amount(deposit_amount),
    }
    res = await client.table("reservations").insert(row).execute()
    return (res.data or [{}])[0]


async def update_reservation(
    res_id: int,
    program: str,
    time_slot: str = "",
    customer_name: str = "",
    people: int = 1,
    platform: str = "현장",
    memo: str = "",
    amount: int = 0,
    payment_method: str = "계좌이체",
    deposit_amount: int = 0,
    date: str = "",
) -> dict:
    """예약 1건 수정."""
    client = await get_supabase()
    pay = (payment_method or "계좌이체").strip()
    if pay not in PAYMENT_METHODS:
        pay = "계좌이체"
    patch = {
        "program": program,
        "time_slot": (time_slot or "").strip(),
        "customer_name": (customer_name or "").strip(),
        "people": max(int(people or 1), 1),
        "platform": (platform or "현장").strip(),
        "memo": (memo or "").strip(),
        "amount": _to_amount(amount),
        "payment_method": pay,
        "deposit_amount": _to_amount(deposit_amount),
    }
    if date and re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        patch["slot_date"] = date
    res = (
        await client.table("reservations")
        .update(patch)
        .eq("id", res_id)
        .execute()
    )
    return (res.data or [{}])[0]


async def delete_reservation(res_id: int):
    """예약 1건 삭제."""
    client = await get_supabase()
    await client.table("reservations").delete().eq("id", res_id).execute()


async def set_reservation_status(res_id: int, status: str) -> dict:
    """예약 상태 변경 ('예약' / '입금대기' / '노쇼' / '취소').

    - 입금대기: 선결제 대기 가예약. 잔여석은 점유(자리 잡아둠)하되
      수입/확정 통계엔 안 잡힘. 입금 확인되면 '예약'으로 확정.
    - 노쇼: 잔여석 집계에서 제외(자리 복구)되지만 기록은 남음. → 노쇼율 통계.
    - 취소: 기록은 보존하되 잔여석·수입·노쇼율 등 모든 통계에서 제외.
    """
    status = (status or "예약").strip()
    if status not in ("예약", "노쇼", "입금대기", "취소"):
        status = "예약"
    client = await get_supabase()
    res = (
        await client.table("reservations")
        .update({"status": status})
        .eq("id", res_id)
        .execute()
    )
    return (res.data or [{}])[0]


async def get_reservations(date_str: str) -> list[dict]:
    """해당 날짜의 모든 예약 건 (사장님 대시보드용, 예약자 정보 포함)."""
    client = await get_supabase()
    res = (
        await client.table("reservations")
        .select("id,slot_date,program,time_slot,customer_name,people,platform,memo,amount,status,payment_method,deposit_amount")
        .eq("slot_date", date_str)
        .order("time_slot")
        .order("id")
        .execute()
    )
    return res.data or []


async def get_recent_reservations(limit: int = 200) -> list[dict]:
    """최근 예약 건 (홈 대시보드 예약확정고객/수입 상세용). 최신 날짜순."""
    client = await get_supabase()
    res = (
        await client.table("reservations")
        .select("id,slot_date,program,time_slot,customer_name,people,platform,memo,amount,status,payment_method,deposit_amount")
        .order("slot_date", desc=True)
        .order("time_slot")
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


async def get_reservation_stats() -> dict:
    """홈 대시보드용 예약확정·수입 요약.

    예약확정 = reservations 테이블의 입력 건(사장님이 직접 확정 입력한 것).
    수입 = 각 예약의 amount(실수령 금액) 합산.
    """
    client = await get_supabase()
    today = today_str()
    ym = today[:7]  # YYYY-MM (이번 달)
    res = (
        await client.table("reservations")
        .select("slot_date,people,amount,status")
        .execute()
    )
    all_rows = res.data or []

    def amt(r):
        return _to_amount(r.get("amount"))

    def status_of(r):
        return (r.get("status") or "예약")

    def is_noshow(r):
        return status_of(r) == "노쇼"

    def is_pending(r):
        return status_of(r) == "입금대기"

    def is_canceled(r):
        return status_of(r) == "취소"

    # 취소 건은 기록만 보존 — 모든 통계(분모 포함)에서 제외
    canceled_total = sum(1 for r in all_rows if is_canceled(r))
    all_rows = [r for r in all_rows if not is_canceled(r)]

    # 예약확정/수입 = '예약'만. 입금대기(미입금)·노쇼는 수입에서 제외.
    rows = [r for r in all_rows if status_of(r) == "예약"]    # 확정 건만
    noshow_rows = [r for r in all_rows if is_noshow(r)]        # 노쇼 건만
    pending_rows = [r for r in all_rows if is_pending(r)]      # 입금대기 건만

    total_reservations = len(rows)
    total_people = sum(int(r.get("people") or 0) for r in rows)
    total_revenue = sum(amt(r) for r in rows)

    today_rows = [r for r in rows if (r.get("slot_date") or "") == today]
    today_reservations = len(today_rows)
    today_people = sum(int(r.get("people") or 0) for r in today_rows)
    today_revenue = sum(amt(r) for r in today_rows)

    month_rows = [r for r in rows if (r.get("slot_date") or "")[:7] == ym]
    month_reservations = len(month_rows)
    month_people = sum(int(r.get("people") or 0) for r in month_rows)
    month_revenue = sum(amt(r) for r in month_rows)

    # 노쇼율 = 노쇼 건 / 전체 입력 건 (확정 + 노쇼)
    total_all = len(all_rows)
    noshow_total = len(noshow_rows)
    noshow_rate = round(noshow_total / total_all * 100, 1) if total_all else 0.0

    month_all = [r for r in all_rows if (r.get("slot_date") or "")[:7] == ym]
    month_noshow = sum(1 for r in month_all if is_noshow(r))
    month_noshow_rate = round(month_noshow / len(month_all) * 100, 1) if month_all else 0.0

    # 입금대기(가예약) = 자리는 잡았지만 아직 입금 안 된 건. 입금 들어올 예상 수입.
    pending_total = len(pending_rows)
    pending_people = sum(int(r.get("people") or 0) for r in pending_rows)
    pending_amount = sum(amt(r) for r in pending_rows)

    return {
        "total_reservations": total_reservations,
        "total_people": total_people,
        "total_revenue": total_revenue,
        "today_reservations": today_reservations,
        "today_people": today_people,
        "today_revenue": today_revenue,
        "month_reservations": month_reservations,
        "month_people": month_people,
        "month_revenue": month_revenue,
        "month": ym,
        # ── 노쇼 지표 ──
        "noshow_total": noshow_total,
        "noshow_rate": noshow_rate,
        "month_noshow": month_noshow,
        "month_noshow_rate": month_noshow_rate,
        "total_all": total_all,
        "canceled_total": canceled_total,
        # ── 입금대기(선결제 가예약) 지표 ──
        "pending_total": pending_total,
        "pending_people": pending_people,
        "pending_amount": pending_amount,
    }


async def get_reservations_range(start: str, end: str) -> list[dict]:
    """기간 내 예약 건 (슬롯 합산용). 예약자 이름은 가져오지만 챗봇엔 안 씀."""
    client = await get_supabase()
    res = (
        await client.table("reservations")
        .select("slot_date,program,time_slot,people,status")
        .gte("slot_date", start)
        .lte("slot_date", end)
        .order("slot_date")
        .execute()
    )
    return res.data or []


def aggregate(rows: list[dict]) -> dict[tuple, int]:
    """(날짜, 종목, 시간) → 인원 합계. 노쇼·취소 건은 제외(자리 복구)."""
    agg: dict[tuple, int] = {}
    for r in rows:
        if (r.get("status") or "예약") in ("노쇼", "취소"):
            continue
        k = (r["slot_date"], r["program"], r.get("time_slot") or "")
        agg[k] = agg.get(k, 0) + (r.get("people") or 0)
    return agg


async def get_day_summary(date_str: str) -> list[dict]:
    """해당 날짜 슬롯별 잔여 요약 (대시보드 상단용).

    정원 있는 종목의 정규 슬롯만 계산. 협의 종목은 제외.
    """
    rows = await get_reservations(date_str)
    agg: dict[tuple, int] = {}
    for r in rows:
        if (r.get("status") or "예약") in ("노쇼", "취소"):
            continue  # 노쇼·취소는 자리 복구 → 집계 제외
        agg[(r["program"], r.get("time_slot") or "")] = (
            agg.get((r["program"], r.get("time_slot") or ""), 0) + (r.get("people") or 0)
        )
    out = []
    for p in PROGRAMS:
        cap = p["capacity"]
        if cap is None:
            continue
        for s in p["slots"]:
            booked = agg.get((p["key"], s), 0)
            out.append({
                "program": p["key"],
                "time_slot": s,
                "booked": booked,
                "capacity": cap,
                "remaining": max(cap - booked, 0),
                "is_full": booked >= cap,
            })
    return out


# ────────────────────────────── 챗봇 주입 텍스트 ──────────────────────────────

async def build_availability_text(days: int = 21) -> str:
    """시스템 프롬프트에 주입할 '마감된 타임' 목록.

    ★ 마감된 슬롯만 넣는다. 시스템 프롬프트가 이 블록을 "마감된 타임만 표시"로
      설명하고 "여기 없으면 예약 가능"이라는 규칙으로 읽기 때문이다. 여유 있는
      슬롯을 함께 넣으면 모델이 그것도 마감으로 해석해, 자리가 남았는데도
      손님에게 "불가"라고 답한다.
    ★ 예약자 이름·플랫폼·메모는 절대 포함하지 않는다.
    ★ days는 agent.build_calendar_text의 달력 길이(21일)와 같아야 한다. 짧으면
      달력에는 있는데 마감 정보가 없는 날이 생겨 "예약 가능"으로 잘못 답한다.
    """
    start = today_str()
    end = (datetime.now(KST) + timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        rows = await get_reservations_range(start, end)
    except Exception as e:
        logger.warning(f"예약현황 조회 실패: {e}")
        return "예약 현황을 일시적으로 확인할 수 없습니다. 정확한 자리는 전화로 확인해 주세요."

    all_open = f"오늘({start}) 기준 전 종목·전 시간대 예약 가능합니다."
    if not rows:
        return all_open

    by_date: dict[str, list[str]] = {}
    for (d, prog, slot), booked in aggregate(rows).items():
        cap = CAPACITY.get(prog)
        if cap is None:
            continue  # 협의 종목은 정원 개념 없음 → 챗봇엔 안 넣음
        if booked < cap:
            continue  # 자리가 남은 슬롯은 넣지 않는다 (docstring 참조)
        by_date.setdefault(d, []).append(f"{prog} {slot}".strip() + ": 마감")

    if not by_date:
        return all_open

    lines = []
    for d, slots in sorted(by_date.items()):
        lines.append(f"- {d}\n  " + "\n  ".join(sorted(slots)))
    return (
        "아래 목록은 '마감된 타임'만 담고 있습니다. "
        "여기 없는 날짜·종목·시간대는 모두 예약 가능합니다.\n" + "\n".join(lines)
    )