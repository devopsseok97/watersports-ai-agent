import base64, hashlib, hmac, time, urllib.parse
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
    ts = str(int(time.time() * 1000))
    msg = f"{cid}_{ts}"
    digest = hmac.new(csec.encode("UTF-8"), msg.encode("UTF-8"), hashlib.sha256).digest()
    sig = base64.b64encode(digest).decode("UTF-8")
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cid,
        "timestamp": ts,
        "client_secret_sign": sig,
        "type": "SELF",
    })
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            "https://api.commerce.naver.com/external/v1/oauth2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=body.encode("UTF-8"),
        )
    return {
        "status": r.status_code,
        "cid_prefix": cid[:4],
        "cid_len": len(cid),
        "csec_len": len(csec),
        "ts": ts,
        "sig_prefix": sig[:10],
        "response": r.json(),
    }
