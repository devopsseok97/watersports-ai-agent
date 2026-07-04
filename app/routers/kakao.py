from fastapi import APIRouter, HTTPException, Request
from app.config import settings
from app.models.kakao import KakaoWebhookRequest, KakaoWebhookResponse
from app.services.agent import AgentService
from app.services.db import save_conversation
from app.services.slack import notify_inquiry
import logging, asyncio, secrets, time
from collections import deque

logger = logging.getLogger(__name__)
router = APIRouter()
agent_service = AgentService()

BOOKING_KEYWORDS = ["예약", "신청", "하고 싶어", "가능한가요", "얼마예요", "결제"]

# ── 웹훅 보안 (2026-07-04 검수 조치) ─────────────────────────────────────────
# 1) 비밀 경로: /kakao/webhook/{secret} — KAKAO_SECRET_KEY 와 일치해야 처리.
#    카카오 오픈빌더는 커스텀 헤더 서명을 지원하지 않으므로 URL 자체를 비밀로 유지.
# 2) rate limit: user_id당 분당 RATE_LIMIT건 초과 시 AI 호출 없이 안내만 반환
#    (Anthropic 크레딧 소진 방지).

RATE_LIMIT = 8          # 분당 최대 메시지 (실사용자는 도달 어려움)
RATE_WINDOW = 60.0      # 초
_MAX_TRACKED_USERS = 2000
_rate: dict[str, deque] = {}
_legacy_warned = False


def _secret_ok(secret: str) -> bool:
    key = settings.kakao_secret_key or ""
    if not key:
        # 마이그레이션 편의: 키 미설정 시 통과 (레거시 경로도 열려 있으므로 보안 저하 없음)
        return True
    return secrets.compare_digest(secret, key)


def _rate_limited(user_id: str) -> bool:
    """True면 차단. in-memory 슬라이딩 윈도."""
    now = time.monotonic()
    dq = _rate.get(user_id)
    if dq is None:
        if len(_rate) >= _MAX_TRACKED_USERS:
            stale = [k for k, v in _rate.items() if not v or now - v[-1] > RATE_WINDOW]
            for k in stale:
                _rate.pop(k, None)
            # 윈도 내 신규 유저 폭주 시에도 무한 증가 방지 (하드 캡: 오래된 것부터 제거)
            while len(_rate) >= _MAX_TRACKED_USERS:
                _rate.pop(next(iter(_rate)))
        dq = _rate[user_id] = deque()
    while dq and now - dq[0] > RATE_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT:
        return True
    dq.append(now)
    return False


# ── 대화 저장/알림 (백그라운드) ───────────────────────────────────────────────
# asyncio.create_task 참조를 보관하지 않으면 GC가 실행 중 태스크를 수거할 수 있음
# (Python 공식 문서 경고) → set에 보관하고 완료 시 제거.
_bg_tasks: set[asyncio.Task] = set()


def _spawn_record(user_id: str, user_message: str, reply: str):
    task = asyncio.create_task(_record(user_id, user_message, reply))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


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


async def _handle_webhook(request: Request):
    body_bytes = await request.body()

    try:
        payload = KakaoWebhookRequest.model_validate_json(body_bytes)
        user_id = payload.userRequest.user.id
        user_message = payload.userRequest.utterance[:1500]
    except Exception as e:
        # 스키마가 달라도 응답에 필요한 건 utterance/user.id뿐 → 원본 dict에서 직접 추출
        # (원본 페이로드를 로그에 남겨 다음 형식 변경 때 즉시 진단 가능하게 한다)
        logger.warning(f"페이로드 파싱 실패: {e} / 원본: {body_bytes[:500]!r}")
        try:
            import json
            raw = json.loads(body_bytes)
            ur = raw.get("userRequest") or {}
            user_message = str(ur.get("utterance") or "")[:1500]
            user_id = str((ur.get("user") or {}).get("id") or "unknown")
            if not user_message:
                return KakaoWebhookResponse.from_text("안녕하세요! 무엇을 도와드릴까요?")
        except Exception:
            return KakaoWebhookResponse.from_text("안녕하세요! 무엇을 도와드릴까요?")

    if _rate_limited(user_id):
        logger.warning(f"[{user_id}] rate limit 초과 — AI 호출 생략")
        return KakaoWebhookResponse.from_text(
            "메시지를 너무 빠르게 보내고 계세요 🙏 잠시 후 다시 말씀해 주세요.\n"
            "급하신 경우 전화 주세요 📞 010-6547-1067"
        )

    logger.info(f"[{user_id}] 메시지: {user_message}")

    reply = await _safe_reply(user_id, user_message)
    _spawn_record(user_id, user_message, reply)
    return KakaoWebhookResponse.from_text(reply)


@router.post("/webhook/{secret}")
async def kakao_webhook_secure(secret: str, request: Request):
    """비밀 경로 웹훅 — 오픈빌더 스킬 URL을 이 경로로 설정한다."""
    if not _secret_ok(secret):
        raise HTTPException(status_code=404)
    return await _handle_webhook(request)


@router.post("/webhook")
async def kakao_webhook(request: Request):
    """레거시 경로 — KAKAO_SECRET_KEY 설정 후에는 404 (비밀 경로만 허용)."""
    global _legacy_warned
    if settings.kakao_secret_key:
        raise HTTPException(status_code=404)
    if not _legacy_warned:
        logger.warning("KAKAO_SECRET_KEY 미설정 — 무인증 레거시 웹훅으로 동작 중 (설정 강력 권장)")
        _legacy_warned = True
    return await _handle_webhook(request)