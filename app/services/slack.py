import httpx
from app.config import settings
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


async def notify_inquiry(
    user_id: str,
    message: str,
    is_booking: bool = False,
    is_escalation: bool = False,
):
    """모든 카카오 문의를 슬랙으로 알림.

    유형별 헤더:
    - 🆘 AI 한계 → 직접 상담 필요
    - 📅 예약 의향 고객
    - 💬 새 문의 (일반)
    """
    now = datetime.now(KST).strftime("%m/%d %H:%M")

    if is_escalation:
        title = "🆘 직접 상담 필요 — AI가 전화 안내함"
    elif is_booking:
        title = "📅 예약 의향 고객 감지!"
    else:
        title = "💬 새 카카오 문의"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*시간:*\n{now}"},
                    {"type": "mrkdwn", "text": f"*고객 ID:*\n`{user_id[:8]}...`"},
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*고객 메시지:*\n>{message}"}
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "카카오 채널 관리자센터에서 대화 전체를 볼 수 있어요 💬"}]
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.slack_webhook_url, json=payload)
            response.raise_for_status()
    except Exception as e:
        logger.warning(f"슬랙 알림 전송 실패: {e}")


async def notify_owner(user_id: str, message: str):
    """하위 호환용 — notify_inquiry로 위임."""
    await notify_inquiry(user_id, message, is_booking=True)
