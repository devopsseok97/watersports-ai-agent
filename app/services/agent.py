import anthropic
from app.config import settings
from app.services.weather import get_operation_status

# 업체별 설정 (나중에 DB로 이전)
SHOP_CONFIG = {
    "default": {
        "name": "포시즌카약패들보드윈드서핑",
        "sports": ["윈드서핑", "패들보드", "카약", "e포일"],
        "prices": {
            "카약": "3만원",
            "패들보드": "3만원 (강습 추가 시 +2만원)",
            "e포일": "15만원",
            "윈드서핑": "12만원",
            "패들보드 스냅사진 패키지": "12만원",
        },
        "hours": """
- 선라이즈 카약/패들보드: 05:10~07:10 (일출 시간에 따라 조정)
- 데이 카약/패들보드: 10:00~12:00 / 13:00~15:00 / 15:00~17:00
- 선셋 카약/패들보드 (평일): 17:30~19:30 (5월부터 18:00 시작, 일몰 시간에 따라 조정)
- 선셋 카약/패들보드 (주말): 17:30~19:30 (5월부터 18:00 시작, 일몰 시간에 따라 조정)
- 화요일 휴무""",
        "location": "서울 광진구 강변북로 2326 서울윈드서핑장 1번 포시즌",
        "contact": "010-6547-1067",
        "beginner_ok": True,
        "min_age": 6,
        "reservation_method": "네이버 스마트스토어 예약 또는 개인 연락(010-6547-1067) 가능합니다.",
    }
}

# 사용자별 대화 기록 (메모리, 나중에 Redis로 이전 가능)
conversation_history: dict[str, list[dict]] = {}
MAX_HISTORY = 10  # 최근 10턴 유지


def build_system_prompt(shop_key: str = "default", weather_status: str = "") -> str:
    shop = SHOP_CONFIG.get(shop_key, SHOP_CONFIG["default"])
    prices_text = "\n".join([f"  - {k}: {v}" for k, v in shop["prices"].items()])

    return f"""당신은 {shop['name']}의 AI 고객 상담 직원입니다.
친절하고 간결하게 답변하세요. 답변은 3-4문장 이내로 유지하세요.
당신은 24시간 응답 가능한 AI입니다. 운영시간은 현장 운영 시간이며, 시간과 관계없이 항상 문의에 답변하세요.

[업체 정보]
- 종목: {', '.join(shop['sports'])}
- 운영시간: {shop['hours']}
- 위치: {shop['location']}
- 문의전화: {shop['contact']}
- 초보자 가능 여부: {'가능합니다' if shop['beginner_ok'] else '불가합니다'}
- 최소 연령: {shop['min_age']}세 이상

[요금]
{prices_text}

[예약 방법]
{shop['reservation_method']}

[오늘 날씨/운영 상태]
{weather_status if weather_status else '운영 중입니다.'}

[주의사항]
- 모르는 정보는 "정확한 내용은 전화로 문의해 주세요 📞 {shop['contact']}"라고 안내하세요.
- 욕설, 광고, 비상업적 대화에는 정중히 거절하세요.
- 예약 확정은 직접 하지 말고 사장님 확인 후 안내 예정이라고 하세요.
"""


class AgentService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def get_reply(self, user_id: str, message: str, shop_key: str = "default") -> str:
        # 날씨 기반 운영 상태 조회
        weather_status = await get_operation_status()

        # 대화 기록 초기화
        if user_id not in conversation_history:
            conversation_history[user_id] = []

        # 대화 기록에 사용자 메시지 추가
        conversation_history[user_id].append({"role": "user", "content": message})

        # 최근 N턴만 유지
        history = conversation_history[user_id][-MAX_HISTORY * 2:]

        try:
            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",  # 빠르고 저렴
                max_tokens=300,
                system=build_system_prompt(shop_key, weather_status),
                messages=history,
            )
            reply = response.content[0].text

        except Exception as e:
            reply = "죄송해요, 잠시 오류가 발생했어요. 전화로 문의해 주세요 📞"

        # 대화 기록에 AI 응답 추가
        conversation_history[user_id].append({"role": "assistant", "content": reply})

        return reply
