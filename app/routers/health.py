import base64, time, urllib.parse
import bcrypt
import httpx
from fastapi import APIRouter
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/ip")
async def get_server_ip():
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get("https://api.ipify.org?format=json")
    return r.json()


@router.get("/naver-test")
async def naver_token_test():
    cid = settings.naver_client_id.strip()
    csec = settings.naver_client_secret.strip()
    ts = str(int((time.time() - 3) * 1000))
    password = f"{cid}_{ts}"
    hashed = bcrypt.hashpw(password.encode("UTF-8"), csec.encode("UTF-8"))
    sig = base64.b64encode(hashed).decode("UTF-8")

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            "https://api.commerce.naver.com/external/v1/oauth2/token",
            data={"grant_type": "client_credentials", "client_id": cid, "timestamp": ts, "client_secret_sign": sig, "type": "SELF"},
        )
    return {"status": r.status_code, "response": r.json()}
