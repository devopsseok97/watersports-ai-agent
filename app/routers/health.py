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
    form_data = {
        "grant_type": "client_credentials",
        "client_id": cid,
        "timestamp": ts,
        "client_secret_sign": sig,
        "type": "SELF",
    }
    body_encoded = urllib.parse.urlencode(form_data)

    # 방법 A: httpx data= 파라미터
    async with httpx.AsyncClient(timeout=10) as c:
        r_a = await c.post(
            "https://api.commerce.naver.com/external/v1/oauth2/token",
            data=form_data,
        )
        # 방법 B: 수동 urlencode (기존 방식)
        r_b = await c.post(
            "https://api.commerce.naver.com/external/v1/oauth2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=body_encoded.encode("UTF-8"),
        )

    return {
        "sig": sig,
        "body_sent": body_encoded,
        "method_a_status": r_a.status_code,
        "method_a_response": r_a.json(),
        "method_b_status": r_b.status_code,
        "method_b_response": r_b.json(),
    }
