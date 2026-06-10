import httpx
from app.config import settings
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


async def notify_owner(user_id: str, message: str):
    """예약 의향 감지 시 사장님 슬랙 알림"""
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🔔 예약 의향 고객 감지!"}
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
                "elements": [{"type": "mrkdwn", "text": "카카오 채널에서 직접 확인 후 답변해 주세요 💬"}]
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.slack_webhook_url, json=payload)
            response.raise_for_status()
    except Exception as e:
        logger.warning(f"슬랙 알림 전송 실패: {e}")
