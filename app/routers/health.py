import httpx
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/ip")
async def get_server_ip():
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get("https://api.ipify.org?format=json")
    return r.json()
