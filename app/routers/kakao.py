from fastapi import APIRouter, Request
from app.models.kakao import KakaoWebhookRequest, KakaoWebhookResponse
from app.services.agent import AgentService
from app.services.db import save_conversation
from app.services.slack import notify_inquiry
import logging, asyncio

logger = logging.getLogger(__name__)
router = APIRouter()
agent_service = AgentService()

# 예약 의향 감지 키워드
BOOKING_KEYWORDS = ["예약", "신청", "하고 싶어", "가능한가요", "얼마예요", "결제"]


@router.get("/webhook")
async def kakao_webhook_check():
    """브라우저/상태 점검용 (카카오는 POST를 씀)."""
    return {"status": "ok", "message": "kakao webhook alive"}


@router.post("/webhook")
async def kakao_webhook(request: Request):
    body_bytes = await request.body()

    # 페이로드 파싱 — 실패해도 거부하지 않고 안내 메시지로 응답(스킬 등록 테스트 통과용)
    try:
        payload = KakaoWebhookRequest.model_validate_json(body_bytes)
        user_id = payload.userRequest.user.id
        user_message = payload.userRequest.utterance
    except Exception as e:
        logger.warning(f"페이로드 파싱 실패(테스트 요청일 수 있음): {e}")
        return KakaoWebhookResponse.from_text("안녕하세요! 무엇을 도와드릴까요?")

    # 지나치게 긴 메시지 자르기 (카카오 공식 한도 1,000자, 여유분 포함)
    user_message = user_message[:1500]

    logger.info(f"[{user_id}] 메시지: {user_message}")

    # AI 응답 생성
    try:
        reply = await agent_service.get_reply(user_id=user_id, message=user_message)
    except Exception as e:
        logger.error(f"AI 응답 생성 실패: {e}")
        reply = "죄송해요, 잠시 오류가 발생했어요. 전화로 문의해 주세요 📞"

    # 예약 의향 감지
    is_booking_intent = any(kw in user_message for kw in BOOKING_KEYWORDS)

    # AI가 전화 안내로 넘긴 경우 감지 (직접 상담 필요 신호)
    is_escalation = "전화로 문의" in reply or "전화 문의" in reply

    # 대화 기록 저장 + 슬랙 알림 — 백그라운드로 처리해 응답 지연 없음
    async def _post_response():
        try:
            await save_conversation(
                user_id=user_id,
                user_message=user_message,
                bot_reply=reply,
                is_booking_intent=is_booking_intent,
            )
        except Exception as e:
            logger.warning(f"대화 저장 실패: {e}")
        await notify_inquiry(
            user_id=user_id,
            message=user_message,
            is_booking=is_booking_intent,
            is_escalation=is_escalation,
            bot_reply=reply,
        )
    asyncio.create_task(_post_response())

    return KakaoWebhookResponse.from_text(reply)
