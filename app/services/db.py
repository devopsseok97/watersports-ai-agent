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


async def save_conversation(user_id: str, user_message: str, bot_reply: str):
    """대화 기록을 Supabase에 저장"""
    client = await get_supabase()
    await client.table("conversations").insert({
        "user_id": user_id,
        "user_message": user_message,
        "bot_reply": bot_reply,
    }).execute()
