from fastapi import APIRouter, Request, HTTPException
from app.models.kakao import KakaoWebhookRequest, KakaoWebhookResponse
from app.services.agent import AgentService
from app.services.db import save_conversation
from app.services.slack import notify_owner
from app.config import settings
import hmac, hashlib, logging, asyncio

logger = logging.getLogger(__name__)
router = APIRouter()
agent_service = AgentService()

# 예약 의향 감지 키워드
BOOKING_KEYWORDS = ["예약", "신청", "하고 싶어", "가능한가요", "얼마예요", "결제"]


def verify_kakao_signature(request_body: bytes, signature: str) -> bool:
    """카카오 웹훅 요청 서명 검증"""
    if not settings.kakao_secret_key:
        return True  # 개발 환경에서는 검증 스킵
    expected = hmac.new(
        settings.kakao_secret_key.encode(), request_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def kakao_webhook(request: Request):
    body_bytes = await request.body()

    # 서명 검증 (프로덕션)
    signature = request.headers.get("X-Kakao-Signature", "")
    if signature and not verify_kakao_signature(body_bytes, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = KakaoWebhookRequest.model_validate_json(body_bytes)
    except Exception as e:
        logger.error(f"페이로드 파싱 오류: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    user_id = payload.userRequest.user.id
    user_message = payload.userRequest.utterance

    logger.info(f"[{user_id}] 메시지: {user_message}")

    # AI 응답 생성
    reply = await agent_service.get_reply(user_id=user_id, message=user_message)

    # 대화 기록 저장 (비동기, 실패해도 응답은 반환)
    try:
        await save_conversation(
            user_id=user_id,
            user_message=user_message,
            bot_reply=reply,
        )
    except Exception as e:
        logger.warning(f"대화 저장 실패: {e}")

    # 예약 의향 감지 → 사장님 슬랙 알림 (백그라운드)
    if any(kw in user_message for kw in BOOKING_KEYWORDS):
        asyncio.create_task(notify_owner(user_id=user_id, message=user_message))

    return KakaoWebhookResponse.from_text(reply)
