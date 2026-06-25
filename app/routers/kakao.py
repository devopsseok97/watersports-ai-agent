from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.models.kakao import KakaoWebhookRequest, KakaoWebhookResponse
from app.services.agent import AgentService
from app.services.db import save_conversation
from app.services.slack import notify_inquiry
import logging, asyncio, httpx

logger = logging.getLogger(__name__)
router = APIRouter()
agent_service = AgentService()

# 예약 의향 감지 키워드
BOOKING_KEYWORDS = ["예약", "신청", "하고 싶어", "가능한가요", "얼마예요", "결제"]

# 콜백 블록에서 손님에게 먼저 보내는 '준비중' 안내 (실제 답변은 곧 콜백으로 도착)
CALLBACK_WAIT_TEXT = "답변을 준비하고 있어요! 잠시만 기다려 주세요 🙏"


async def _safe_reply(user_id: str, user_message: str) -> str:
    """AI 답변 생성 (실패해도 반드시 안내 문구 반환)."""
    try:
        return await agent_service.get_reply(user_id=user_id, message=user_message)
    except Exception as e:
        logger.error(f"AI 응답 생성 실패: {e}")
        return "죄송해요, 잠시 오류가 발생했어요. 전화로 문의해 주세요 📞 010-6547-1067"


async def _record(user_id: str, user_message: str, reply: str):
    """대화 저장 + 슬랙 알림 (동기·콜백 경로 공용, 백그라운드 실행)."""
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


async def _callback_flow(callback_url: str, user_id: str, user_message: str):
    """콜백 경로: 5초 제한 없이 AI 답변 생성 후 callbackUrl로 최종 말풍선 전송."""
    reply = await _safe_reply(user_id, user_message)
    payload = KakaoWebhookResponse.from_text(reply).model_dump()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(callback_url, json=payload)
            if r.status_code != 200:
                logger.warning(f"콜백 전송 실패 {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"콜백 전송 오류: {e}")
    await _record(user_id, user_message, reply)


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
        user_message = payload.userRequest.utterance[:1500]  # 카카오 한도 여유분
        callback_url = payload.userRequest.callbackUrl
    except Exception as e:
        logger.warning(f"페이로드 파싱 실패(테스트 요청일 수 있음): {e}")
        return KakaoWebhookResponse.from_text("안녕하세요! 무엇을 도와드릴까요?")

    logger.info(f"[{user_id}] 메시지: {user_message}{' (콜백)' if callback_url else ''}")

    # 콜백 블록(승인·활성화된 경우): 즉시 '준비중'으로 응답하고
    # 백그라운드에서 AI 답변을 만들어 callbackUrl로 최종 전송 → 5초 타임아웃 경주 제거
    if callback_url:
        asyncio.create_task(_callback_flow(callback_url, user_id, user_message))
        return JSONResponse({
            "version": "2.0",
            "useCallback": True,
            "data": {"text": CALLBACK_WAIT_TEXT},
        })

    # 콜백 미사용(승인 전 또는 일반 블록): 기존 동기 응답 흐름 그대로
    reply = await _safe_reply(user_id, user_message)
    asyncio.create_task(_record(user_id, user_message, reply))
    return KakaoWebhookResponse.from_text(reply)
