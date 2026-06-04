from supabase import acreate_client
from app.config import settings
import logging

logger = logging.getLogger(__name__)

_supabase = None


async def get_supabase():
    global _supabase
    if _supabase is None:
        _supabase = await acreate_client(settings.supabase_url, settings.supabase_key)
    return _supabase


async def save_conversation(
    user_id: str,
    user_message: str,
    bot_reply: str,
    is_booking_intent: bool = False,
):
    """대화 기록을 Supabase에 저장"""
    client = await get_supabase()
    await client.table("conversations").insert({
        "user_id": user_id,
        "user_message": user_message,
        "bot_reply": bot_reply,
        "is_booking_intent": is_booking_intent,
    }).execute()
    # ---------- 대시보드 조회용 ----------

async def get_recent_conversations(limit: int = 100) -> list[dict]:
    """최근 대화 기록 조회 (최신순)"""
    client = await get_supabase()
    res = (
        await client.table("conversations")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


async def get_booking_intents(limit: int = 100) -> list[dict]:
    """예약 의향 고객 대화만 조회 (최신순)"""
    client = await get_supabase()
    res = (
        await client.table("conversations")
        .select("*")
        .eq("is_booking_intent", True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


async def get_stats() -> dict:
    """대시보드 상단 요약 지표"""
    from datetime import datetime, timezone, timedelta

    client = await get_supabase()
    total = await client.table("conversations").select("id", count="exact").execute()
    intents = (
        await client.table("conversations")
        .select("id", count="exact")
        .eq("is_booking_intent", True)
        .execute()
    )
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(hours=9)  # KST 기준 자정
    today = (
        await client.table("conversations")
        .select("id", count="exact")
        .gte("created_at", today_start.isoformat())
        .execute()
    )
    return {
        "total_conversations": total.count or 0,
        "booking_intents": intents.count or 0,
        "today_conversations": today.count or 0,
    }