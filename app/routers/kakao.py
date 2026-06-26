from fastapi import APIRouter, Request
from app.models.kakao import KakaoWebhookRequest, KakaoWebhookResponse
from app.services.agent import AgentService
from app.services.db import save_conversation
from app.services.slack import notify_inquiry
import logging, asyncio

logger = logging.getLogger(__name__)
router = APIRouter()
agent_service = AgentService()

BOOKING_KEYWORDS = ["예약", "신청", "하고 싶어", "가능한가요", "얼마예요", "결제"]


async def _safe_reply(user_id: str, user_message: str) -> str:
    try:
        return await agent_service.get_reply(user_id=user_id, message=user_message)
    except Exception as e:
        logger.error(f"AI 응답 생성 실패: {e}")
        return "죄송해요, 잠시 오류가 발생했어요. 전화로 문의해 주세요 📞 010-6547-1067"


async def _record(user_id: str, user_message: str, reply: str):
    is_booking_intent = any(kw in user_message for kw in BOOKING_KEYWORDS)
    is_escalation = "전화로 문의" in reply or "전화 문의" in reply
    try:
        await save_conversation(
            user_id=user_id,
            user_message=user_message,
            bot_reply=reply,
            is_booking_intent=is_booking_intent,
        )
    except Exception as e:
        logger.warning(f"대화 저장 실패: {e}")
    try:
        await notify_inquiry(
            user_id=user_id,
            message=user_message,
            is_booking=is_booking_intent,
            is_escalation=is_escalation,
            bot_reply=reply,
        )
    except Exception as e:
        logger.warning(f"슬랙 알림 실패: {e}")


@router.get("/webhook")
async def kakao_webhook_check():
    return {"status": "ok", "message": "kakao webhook alive"}


@router.post("/webhook")
async def kakao_webhook(request: Request):
    body_bytes = await request.body()

    try:
        payload = KakaoWebhookRequest.model_validate_json(body_bytes)
        user_id = payload.userRequest.user.id
        user_message = payload.userRequest.utterance[:1500]
    except Exception as e:
        logger.warning(f"페이로드 파싱 실패: {e}")
        return KakaoWebhookResponse.from_text("안녕하세요! 무엇을 도와드릴까요?")

    logger.info(f"[{user_id}] 메시지: {user_message}")

    reply = await _safe_reply(user_id, user_message)
    asyncio.create_task(_record(user_id, user_message, reply))
    return KakaoWebhookResponse.from_text(reply)
