"""사진 앨범 메타데이터 관리 (Supabase).

사진 파일 자체는 서버 로컬 폴더(photo_storage/{code}/)에 저장하고,
앨범 정보(코드, 메모, 사진 수, 만료일)만 Supabase에 기록한다.
"""
import secrets
import string
import logging
from datetime import datetime, timezone, timedelta

from app.services.db import get_supabase

logger = logging.getLogger(__name__)

EXPIRE_DAYS = 7
_ALPHABET = string.ascii_uppercase + string.digits
# 헷갈리는 글자 제외 (0,O,1,I)
_ALPHABET = _ALPHABET.replace("0", "").replace("O", "").replace("1", "").replace("I", "")


def generate_code(length: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


async def create_album(memo: str = "") -> dict:
    """새 앨범 생성. 고유 코드 발급."""
    client = await get_supabase()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=EXPIRE_DAYS)

    # 코드 충돌 방지 (최대 5회 재시도)
    for _ in range(5):
        code = generate_code()
        existing = (
            await client.table("photo_albums").select("id").eq("code", code).execute()
        )
        if not existing.data:
            break

    res = (
        await client.table("photo_albums")
        .insert({
            "code": code,
            "memo": memo or "",
            "photo_count": 0,
            "expires_at": expires.isoformat(),
        })
        .execute()
    )
    return res.data[0]


async def get_album(code: str) -> dict | None:
    client = await get_supabase()
    res = await client.table("photo_albums").select("*").eq("code", code).execute()
    return res.data[0] if res.data else None


async def list_albums(limit: int = 100) -> list[dict]:
    client = await get_supabase()
    res = (
        await client.table("photo_albums")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


async def set_photo_count(code: str, count: int):
    client = await get_supabase()
    await client.table("photo_albums").update({"photo_count": count}).eq(
        "code", code
    ).execute()


async def delete_album(code: str):
    client = await get_supabase()
    await client.table("photo_albums").delete().eq("code", code).execute()


async def list_expired_albums() -> list[dict]:
    client = await get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    res = (
        await client.table("photo_albums")
        .select("*")
        .lt("expires_at", now)
        .execute()
    )
    return res.data or []


def is_expired(album: dict) -> bool:
    exp = album.get("expires_at")
    if not exp:
        return False
    try:
        exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
    except Exception:
        return False
    return datetime.now(timezone.utc) > exp_dt