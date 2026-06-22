"""네이버 스마트스토어 주문 자동 동기화.

5분마다 최근 15분 결제완료 주문을 조회해 예약 DB에 자동 등록.
"""
import base64
import logging
import re
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import bcrypt

import httpx

from app.config import settings
from app.services import availability as av

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
NAVER_API = "https://api.commerce.naver.com/external"

_token_cache: dict = {}
_processed: set[str] = set()  # 처리된 productOrderId (메모리)
_last_ip_alert: float = 0  # IP 변경 알림 마지막 발송 시각


# ── 인증 ──────────────────────────────────────────────────────────────────────

def _sign(client_id: str, client_secret: str) -> tuple[str, str]:
    ts = str(int((time.time() - 3) * 1000))  # 3초 전 타임스탬프 (클럭 스큐 보정)
    password = f"{client_id}_{ts}"
    hashed = bcrypt.hashpw(password.encode("UTF-8"), client_secret.encode("UTF-8"))
    sig = base64.b64encode(hashed).decode("UTF-8")
    return ts, sig


async def _get_token() -> str:
    now = time.monotonic()
    if _token_cache.get("token") and now < _token_cache.get("exp", 0) - 60:
        return _token_cache["token"]

    cid = settings.naver_client_id.strip()
    csec = settings.naver_client_secret.strip()
    if not cid or not csec:
        raise ValueError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정")

    ts, sig = _sign(cid, csec)
    logger.info(f"[네이버] client_id={cid[:6]}... ts={ts} sig={sig[:10]}...")
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cid,
        "timestamp": ts,
        "client_secret_sign": sig,
        "type": "SELF",
    })
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{NAVER_API}/v1/oauth2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=body.encode("UTF-8"),
        )
        if r.status_code != 200:
            logger.error(f"네이버 토큰 오류 {r.status_code}: {r.text}")
            if r.status_code == 403:
                try:
                    if r.json().get("code") == "GW.IP_NOT_ALLOWED":
                        await _alert_ip_change()
                except Exception:
                    pass
            r.raise_for_status()
        d = r.json()

    _token_cache["token"] = d["access_token"]
    _token_cache["exp"] = now + int(d.get("expires_in", 3600))
    return _token_cache["token"]


# ── 파싱 헬퍼 ─────────────────────────────────────────────────────────────────

def _parse_date(raw: str) -> str | None:
    """자유 텍스트 이용날짜 → YYYY-MM-DD."""
    if not raw:
        return None
    year = datetime.now(KST).year
    raw = raw.strip()

    # YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # M/D  M-D  M.D
    m = re.match(r"(\d{1,2})[/\-.](\d{1,2})", raw)
    if m:
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    # M월 D일
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", raw)
    if m:
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    # MMDD (4자리)
    m = re.match(r"^(\d{2})(\d{2})$", raw)
    if m:
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def _parse_program(name: str, option: str) -> str:
    t = f"{name} {option}".lower()
    if "선셋" in t and "패들" in t:
        return "선셋패들보드"
    if "선셋" in t and "카약" in t:
        return "선셋카약"
    if "패들" in t:
        return "데이패들보드"
    if "카약" in t:
        return "데이카약"
    if "윈드" in t:
        return "윈드서핑"
    if "전동" in t and "포일" in t:
        return "전동e포일"
    if "펌핑" in t:
        return "펌핑포일"
    if "포일" in t or "e포일" in t:
        return "E포일"
    return "데이패들보드"


def _parse_time(option: str) -> str:
    m = re.search(r"(\d{1,2}):(\d{2})", option or "")
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


# ── 중복 체크 ─────────────────────────────────────────────────────────────────

async def _already_saved(order_id: str) -> bool:
    """DB에 같은 네이버 주문번호 메모가 있으면 True."""
    from app.services.db import get_supabase
    suffix = order_id[-8:]
    client = await get_supabase()
    res = await client.table("reservations").select("id").ilike("memo", f"%{suffix}%").execute()
    return bool(res.data)


# ── IP 변경 감지 알림 ────────────────────────────────────────────────────────────

async def _alert_ip_change():
    global _last_ip_alert
    now = time.monotonic()
    if now - _last_ip_alert < 3600:  # 1시간 쿨다운
        return
    _last_ip_alert = now
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            ip_r = await c.get("https://api.ipify.org?format=json")
            current_ip = ip_r.json()["ip"]
        payload = {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "⚠️ 네이버 API IP 변경 알림"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": (
                    f"서버 IP가 변경되어 네이버 스마트스토어 연동이 중단되었습니다.\n\n"
                    f"*새 서버 IP:* `{current_ip}`\n\n"
                    f"👉 *네이버 커머스API 센터* → 앱 수정 → API호출 IP를 `{current_ip}`로 변경 후 저장하세요."
                )}},
            ]
        }
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(settings.slack_webhook_url, json=payload)
        logger.warning(f"[네이버] IP 변경 감지 → 슬랙 알림 발송: {current_ip}")
    except Exception as e:
        logger.warning(f"IP 변경 알림 실패: {e}")


# ── 슬랙 알림 ─────────────────────────────────────────────────────────────────

async def _slack_new_order(name: str, date: str, program: str, time_slot: str,
                            people: int, amount: int, order_id: str):
    payload = {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "🛒 네이버 스마트스토어 신규 주문"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*고객명:*\n{name}"},
                {"type": "mrkdwn", "text": f"*종목:*\n{program}"},
                {"type": "mrkdwn", "text": f"*이용날짜:*\n{date} {time_slot}".strip()},
                {"type": "mrkdwn", "text": f"*인원 / 금액:*\n{people}명 / {amount:,}원"},
            ]},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"주문번호 끝자리: `{order_id[-8:]}` · 예약 관리에 자동 등록되었습니다 ✅"}
            ]},
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(settings.slack_webhook_url, json=payload)
    except Exception as e:
        logger.warning(f"슬랙 알림 실패: {e}")


# ── 메인 동기화 ───────────────────────────────────────────────────────────────

async def sync_naver_orders() -> int:
    """최근 15분 결제완료 주문 동기화. 신규 등록 건수 반환."""
    if not settings.naver_client_id:
        return 0

    try:
        tok = await _get_token()
    except Exception as e:
        logger.warning(f"네이버 토큰 발급 실패: {e}")
        return 0

    headers = {"Authorization": f"Bearer {tok}"}
    since = (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    async with httpx.AsyncClient(timeout=15) as c:
        # 1단계: 최근 15분 결제완료 상품주문 번호 목록
        r = await c.get(
            f"{NAVER_API}/v1/pay-order/seller/product-orders/last-changed-statuses",
            headers=headers,
            params={"lastChangedFrom": since, "lastChangedType": "PAYED"},
        )
        if r.status_code != 200:
            logger.warning(f"네이버 주문 목록 조회 실패: {r.status_code} {r.text[:300]}")
            return 0

        order_ids = [o.get("productOrderId") for o in r.json().get("data", []) if o.get("productOrderId")]
        new_ids = [oid for oid in order_ids if oid not in _processed]
        if not new_ids:
            return 0

        # 2단계: 상품주문 상세 일괄 조회
        r2 = await c.post(
            f"{NAVER_API}/v1/pay-order/seller/product-orders/query",
            headers=headers,
            json={"productOrderIds": new_ids},
        )
        if r2.status_code != 200:
            logger.warning(f"네이버 주문 상세 조회 실패: {r2.status_code} {r2.text[:300]}")
            return 0

        count = 0
        for item in r2.json().get("data", []):
            d = item.get("productOrder", {})
            oid = d.get("productOrderId")
            if not oid:
                continue
            try:
                if await _already_saved(oid):
                    _processed.add(oid)
                    continue

                input_opts = d.get("inputOptions") or []
                date_raw = next(
                    (x.get("inputValue", "") for x in input_opts if "날짜" in x.get("inputLabel", "")),
                    ""
                )
                date_str = _parse_date(date_raw)
                if not date_str:
                    order_date = d.get("orderDate", "")
                    date_str = order_date[:10] if order_date else datetime.now(KST).strftime("%Y-%m-%d")

                product_name = d.get("productName", "")
                option_str = d.get("productOption", "")
                program = _parse_program(product_name, option_str)
                time_slot = _parse_time(option_str)

                orderer = d.get("orderer") or d.get("buyer") or {}
                customer_name = orderer.get("name", "")
                people = max(int(d.get("quantity", 1)), 1)
                amount = int(d.get("totalPaymentAmount", 0))

                await av.add_reservation(
                    date_str=date_str,
                    program=program,
                    time_slot=time_slot,
                    customer_name=customer_name,
                    people=people,
                    platform="네이버",
                    memo=f"스마트스토어#{oid[-8:]}",
                    amount=amount,
                    payment_method="계좌이체",
                    deposit_amount=amount,
                )

                _processed.add(oid)
                count += 1
                logger.info(f"네이버 주문 자동 등록: {oid} → {customer_name} {date_str} {program}")
                await _slack_new_order(customer_name, date_str, program, time_slot, people, amount, oid)

            except Exception as e:
                logger.error(f"네이버 주문 처리 실패 ({oid}): {e}")

    return count
