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
    import base64 as _b64

    sig_urlsafe = _b64.urlsafe_b64encode(digest).decode("UTF-8")

    URL = "https://api.commerce.naver.com/external/v1/oauth2/token"
    results = {}

    async with httpx.AsyncClient(timeout=10) as c:
        # A: type=SELF + 표준 Base64
        r = await c.post(URL, data={"grant_type": "client_credentials", "client_id": cid, "timestamp": ts, "client_secret_sign": sig, "type": "SELF"})
        results["A_SELF_std"] = {"status": r.status_code, "res": r.json()}

        # B: type 없음 + 표준 Base64
        r = await c.post(URL, data={"grant_type": "client_credentials", "client_id": cid, "timestamp": ts, "client_secret_sign": sig})
        results["B_notype_std"] = {"status": r.status_code, "res": r.json()}

        # C: type=SELF + URL-safe Base64
        r = await c.post(URL, data={"grant_type": "client_credentials", "client_id": cid, "timestamp": ts, "client_secret_sign": sig_urlsafe, "type": "SELF"})
        results["C_SELF_urlsafe"] = {"status": r.status_code, "res": r.json()}

        # D: type 없음 + URL-safe Base64
        r = await c.post(URL, data={"grant_type": "client_credentials", "client_id": cid, "timestamp": ts, "client_secret_sign": sig_urlsafe})
        results["D_notype_urlsafe"] = {"status": r.status_code, "res": r.json()}

    return {"sig_std": sig, "sig_urlsafe": sig_urlsafe, "results": results}
