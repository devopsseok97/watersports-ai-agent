import time
import logging
import anthropic
from app.config import settings
from app.services.weather import get_operation_status
from app.services.availability import build_availability_text, today_str

logger = logging.getLogger(__name__)

# 날씨·잔여석 인메모리 캐시 (Railway 재시작 시 초기화)
# ── 중요: 외부 API(KMA/Supabase) 호출은 백그라운드 루프(main.py)에서만 수행한다.
#         카카오 요청 경로에서는 절대 await 하지 않고 캐시 값만 즉시 읽는다.
#         (요청당 추가 지연 ≈ 0초 → 5초 카카오 타임아웃 안전)
_cache: dict = {}
_WEATHER_TTL = 1800  # 30분 (참고용)
_AVAIL_TTL   = 60    # 1분 (참고용)


# ── 백그라운드 갱신 (main.py lifespan 루프에서 호출) ──────────────────────────

async def refresh_weather_cache() -> None:
    """날씨/운영상태 캐시 갱신. 실패해도 직전 값 유지."""
    try:
        val = await get_operation_status()
        _cache["weather"] = (time.monotonic(), val)
    except Exception as e:
        logger.warning(f"날씨 캐시 갱신 실패(직전 값 유지): {e}")


async def refresh_availability_cache() -> None:
    """잔여석 캐시 갱신. 실패해도 직전 값 유지."""
    try:
        val = await build_availability_text()
        _cache["avail"] = (time.monotonic(), val)
    except Exception as e:
        logger.warning(f"잔여석 캐시 갱신 실패(직전 값 유지): {e}")


# ── 읽기 전용 getter (요청 경로에서 사용, 외부 호출 없음) ──────────────────────

def get_cached_weather() -> str:
    return _cache.get("weather", (0, ""))[1]


def get_cached_availability() -> str:
    return _cache.get("avail", (0, ""))[1]

# 업체별 설정 (나중에 DB로 이전)
SHOP_CONFIG = {
    "default": {
        "name": "서퍼스트",
        "sports": ["패들보드", "카약", "윈드서핑", "전동e포일", "E포일", "펌핑포일"],
        "prices": {
            "데이패들보드 (2시간 체험, 정원 20명)": "렌탈 3만원 / 강습포함 5만원",
            "선셋패들보드 (2시간 체험, 정원 20명)": "렌탈 3만원 / 강습포함 5만원",
            "데이카약 (2시간 체험, 정원 40명)": "1인 3만원 (기준: 2인 1대 / 1인 탑승도 가능, 가격 동일)",
            "선셋카약 (2시간 체험, 정원 40명)": "1인 3만원 (기준: 2인 1대 / 1인 탑승도 가능, 가격 동일)",
            "윈드서핑 (3시간 체험, 정원 5명)": "렌탈 8만원 / 강습포함 12만원",
            "전동e포일 (1시간 체험)": "렌탈 8만원 / 강습포함 15만원",
            "E포일 (3시간 체험, 정원 2명)": "렌탈 8만원 / 강습포함 15만원",
            "펌핑포일 (2시간 체험)": "렌탈 7만원 / 강습포함 10만원",
        },
        "hours": """
- 데이 패들보드/카약: 10:00 / 13:00 / 15:00 시작 (각 2시간)
- 선셋 패들보드/카약: 18:30 시작 (일몰 시간에 따라 변동, 2시간)
- 윈드서핑: 09:00 / 13:00 시작 (각 3시간)
- E포일: 09:00 / 13:00 시작 (각 3시간)
- 전동e포일: 시간 협의 후 예약 (1시간)
- 펌핑포일: 시간 협의 후 예약 (2시간)
- 화요일 휴무""",
        "location": "서울 광진구 강변북로 2326 서울윈드서핑장 1번 서퍼스트",
        "contact": "010-6547-1067",
        "beginner_ok": True,
        "min_age": 6,
        "reservation_method": "네이버 스마트스토어 예약 또는 개인 연락(010-6547-1067) 가능합니다.",
        "smartstore_links": {
            "패들보드/카약": "https://smartstore.naver.com/fourseason_1/products/8356965224",
            "전동e포일":     "https://smartstore.naver.com/fourseason_1/products/10160039912",
            "스냅사진":      "https://smartstore.naver.com/fourseason_1/products/12109263589",
            "윈드서핑":      "https://smartstore.naver.com/fourseason_1/products/8357062775",
        },
        "preparation": """- 공통 준비물: 여벌 옷, 수건
- 휴대폰 방수팩: 직접 사진·영상 촬영을 원하시면 개인 방수팩을 꼭 지참해 주세요. (강사님들도 사진을 촬영해 드립니다!)
- 패들보드/윈드서핑/포일류: 물에 빠질 수 있으니 물놀이 복장(젖어도 되는 옷)과 여벌 옷을 준비해 주세요.
- 카약: 물에 빠지지 않으니 편한 복장이면 됩니다. 다만 엉덩이 쪽이 젖을 수 있어 갈아입을 여분의 바지를 추천드립니다. 카약은 간식을 챙겨 오셔서 드셔도 됩니다.
- 분실 주의: 물에 휴대폰 등을 빠뜨릴 위험이 있으며, 분실 시 책임지지 않습니다. 귀중품은 보관 후 이용해 주세요.
- 도착 시간: 손님이 많아 현장이 복잡할 수 있으니, 예약 시간 30분 전 여유 있게 도착하시길 추천드립니다.""",
    }
}

# 사용자별 대화 기록 (메모리, 나중에 Redis로 이전 가능)
conversation_history: dict[str, list[dict]] = {}
MAX_HISTORY = 10   # 유저당 최근 N턴 유지
MAX_USERS = 5000   # 메모리 보호: 최대 보관 유저 수


def build_system_prompt(shop_key: str = "default") -> str:
    """캐시용 정적 시스템 프롬프트 (날씨·날짜·잔여석 제외)."""
    shop = SHOP_CONFIG.get(shop_key, SHOP_CONFIG["default"])
    prices_text = "\n".join([f"  - {k}: {v}" for k, v in shop["prices"].items()])
    links = shop.get("smartstore_links", {})
    smartstore_text = "\n".join([f"  - {k}: {v}" for k, v in links.items()])

    return f"""당신은 {shop['name']}의 AI 고객 상담 직원입니다.
친절하고 간결하게 답변하세요. 핵심만 담아 너무 길지 않게 답하세요.
당신은 24시간 응답 가능한 AI입니다. 운영시간은 현장 운영 시간이며, 시간과 관계없이 항상 문의에 답변하세요.
"내일", "이번 주말" 등은 아래 dynamic 블록의 오늘 날짜를 기준으로 계산하세요.

[답변 형식 - 가독성 매우 중요]
★ 카카오톡은 굵은 글씨·마크다운(**별표**, #, 등)이 표시되지 않습니다.
  별표(**)를 쓰면 손님 화면에 별표가 그대로 보여 지저분합니다. 절대 사용하지 마세요.
강조하고 싶을 땐 별표 대신 이모지 라벨과 줄바꿈으로 표현하세요.

작성 규칙:
1. 한 문장이 끝나면 줄바꿈(엔터)을 넣어 한 줄에 한 내용만 보이게 하세요.
2. 가격·시간·장소 등 항목이 여러 개면 한 줄에 하나씩, 앞에 관련 이모지를 붙이세요.
   (📍 장소 / ⏰ 시간 / 💰 비용 / 👕 준비물 / 🛶 종목 등)
3. 내용 묶음이 바뀌면 빈 줄(엔터 두 번)로 문단을 구분하세요.
4. 첫 인사와 마무리 한마디는 짧고 친근하게, 이모지를 가볍게 곁들이세요 (과하지 않게).

[좋은 답변 예시]
안녕하세요! 서퍼스트입니다 🏄‍♂️

데이패들보드 안내드릴게요!

💰 비용: 렌탈 3만원 / 강습포함 5만원 (1인)
⏰ 시간: 10:00 / 13:00 / 15:00 (2시간 체험)
👕 준비물: 물놀이 복장 (여벌 옷·수건 추천)

초보자도 충분히 즐기실 수 있어요!
예약은 네이버 스마트스토어 또는 전화(010-6547-1067)로 가능합니다 😊

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

[준비물 및 안내사항]
{shop.get('preparation', '')}

[네이버 스마트스토어 결제 링크]
결제·예약을 원하는 손님에게는 아래 해당 링크를 안내하세요.
구매 후 리뷰 작성도 꼭 부탁드리세요 (리뷰가 많을수록 다른 손님에게 도움이 돼요!).
{smartstore_text}
  - E포일/펌핑포일: 링크 없음 → 전화 예약 안내 (010-6547-1067)

결제 링크 안내 규칙 - 매우 중요:
- 손님이 종목 + 날짜를 함께 언급하면 (예: "패들보드 7/4", "카약 이번 주말") → 잔여석 안내 후 즉시 결제 링크를 제공하세요. 추가 질문 없이 바로 링크를 드리세요.
- 손님이 특정 종목에 관심을 보이거나 가격·시간을 물어보면 → 안내 후 마지막에 결제 링크를 함께 제공하세요.
- 손님이 "결제하고 싶다", "예약하려고 한다", "어떻게 신청하나요" 등 결제·예약 의향을 보이면 해당 종목 링크를 바로 제공하세요.
- 링크는 그대로 붙여넣기하여 클릭 가능하게 안내하세요.
- 리뷰 부탁 멘트는 자연스럽게 한 줄만 (예: "이용 후 리뷰도 남겨주시면 감사해요 😊").
- 여러 종목을 함께 예약하려는 경우 각 종목 링크를 모두 안내하세요.
- 스냅사진 링크는 사진 촬영 서비스를 원하는 손님에게 안내하세요.
- E포일/펌핑포일 관심 손님에게는 "전화로 예약 가능합니다 📞 010-6547-1067" 를 바로 안내하세요.

[날짜+종목 언급 시 응답 흐름 - 필수]
손님이 날짜와 종목을 언급하면 반드시 아래 순서로 답하세요:
1. 해당 날짜 잔여석 안내
   - 예약 가능 현황에 해당 날짜·종목이 있으면 → 잔여석 숫자 안내
   - 예약 가능 현황에 해당 날짜·종목이 없으면 → "예약 가능합니다" (전화 문의 유도 금지!)
2. 간단한 요금·시간 안내 (1~2줄)
3. 결제 링크 바로 제공 (해당 종목 스마트스토어 링크)

★ 절대 금지: 현황에 날짜가 없다는 이유로 "전화 문의하세요"라고 하면 안 됩니다.
   현황에 없는 날짜 = 예약 가능한 날짜입니다. 반드시 결제 링크를 제공하세요.

★ 선셋만 언급하고 패들보드/카약을 특정하지 않은 경우: 종목을 묻지 말고 두 링크를 모두 즉시 제공하세요.
★ 날짜 여러 개를 물어본 경우: 날짜도 묻지 마세요. 손님이 직접 고릅니다. 링크를 바로 주세요.
★ 응답은 간결하게. 잔여석 현황 + 요금 한 줄 + 링크. 추가 질문 금지.

[선셋 문의 응답 예시 - 이 형식 그대로 따르세요]
손님: "7월 6,7,8 중에 선셋 예약하고 싶어요"
AI 응답:
안녕하세요! 서퍼스트입니다 🏄

7월 6일(일) 선셋카약 38자리 남음 / 선셋패들보드 예약 가능
7월 7일(월) 전 종목 예약 가능
7월 8일(화) 휴무 😥

💰 선셋카약·패들보드 18:30 / 1인 3만원~5만원

아래 링크에서 원하는 날짜로 예약하세요!
https://smartstore.naver.com/fourseason_1/products/8356965224

이용 후 리뷰 남겨주시면 감사해요 😊

[휴무일 판단 규칙 - 매우 중요]
- 화요일 휴무입니다.
- 날짜가 화요일인지 판단할 때 반드시 아래 오늘 날짜 기준으로 요일을 직접 계산하세요.
- 절대로 날짜를 추측하거나 어림잡지 마세요. 오늘 날짜(dynamic 블록)에서 정확히 계산하세요.
- 화요일이 아닌 날을 화요일이라고 하거나 "화요일 전날"이라고 하면 안 됩니다.

[카약 특이사항 - 중요]
- 카약 기준은 2인 1대 (1대에 2명이 함께 탑승하는 것이 기본)
- 혼자서도 탑승 가능하며 가격은 동일 (1인 3만원)
- 예약은 인당 1개씩: 2명이면 예약 2개, 1명이면 예약 1개
- 손님이 카약 인원/예약 수 물으면 반드시 아래 내용을 포함해 안내:
  "카약은 2인 1카약이고 요금은 인당이라, 2명이시면 예약 2개 해주시면 됩니다!
  혼자서 한 개 카약 타셔도 되고, 가격도 똑같아요 😊
  다만 2인용 카약이라 가급적 2명이서 타시는 걸 추천드려요.
  바람이 거세지면 혼자 앞으로 나아가기가 쉽지 않거든요!"

[주의사항]
- 모르는 정보는 "정확한 내용은 전화로 문의해 주세요 📞 {shop['contact']}"라고 안내하세요.
- 자리 문의 시: 위 '예약 가능 현황'의 잔여 좌석을 그대로 안내하세요. "N자리 남음"이면 그 숫자로 안내 후 결제 링크 제공. 현황에 없는 종목·시간대는 "예약 가능합니다"라고 안내 후 결제 링크 제공. 마감이 임박하면 빠른 예약을 권하세요.
- 잔여석 마감(0석) 시: "해당 시간에는 잔여석이 없습니다 😥\n다른 시간대나 날짜로 변경을 원하시거나 추가 문의는 아래 번호로 연락 주시면 상담 도와드리겠습니다!\n📞 010-6547-1067" 라고 안내하세요. 결제 링크는 제공하지 마세요.
- 욕설, 광고, 비상업적 대화에는 정중히 거절하세요.
- 예약 확정은 직접 하지 말고 사장님 확인 후 안내 예정이라고 하세요.
"""


class AgentService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def get_reply(self, user_id: str, message: str, shop_key: str = "default") -> str:
        import asyncio

        # 날씨·잔여석: 백그라운드가 미리 채워둔 캐시만 즉시 읽음 (외부 호출 없음 → 지연 0)
        weather_status = get_cached_weather()
        availability_status = get_cached_availability()

        # 대화 기록 초기화
        if user_id not in conversation_history:
            # 유저 수 한도 초과 시 가장 오래된 유저부터 제거
            if len(conversation_history) >= MAX_USERS:
                oldest_keys = list(conversation_history.keys())[:MAX_USERS // 10]
                for k in oldest_keys:
                    del conversation_history[k]
            conversation_history[user_id] = []

        # 대화 기록에 사용자 메시지 추가
        conversation_history[user_id].append({"role": "user", "content": message})

        # 최근 N턴만 유지
        history = conversation_history[user_id][-MAX_HISTORY * 2:]

        # 시스템 프롬프트: 정적 블록(캐시) + 동적 블록(날짜·날씨·잔여석)
        dynamic_part = (
            f"오늘 날짜: {today_str()} (KST)\n\n"
            f"[오늘 날씨/운영 상태]\n{weather_status or '운영 중입니다.'}\n\n"
            f"[예약 가능 현황 (마감된 타임만 표시)]\n"
            f"{availability_status or '실시간 현황은 전화로 확인해 주세요.'}"
        )
        system_blocks = [
            {
                "type": "text",
                "text": build_system_prompt(shop_key),
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": dynamic_part},
        ]

        try:
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=400,
                    system=system_blocks,
                    messages=history,
                    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
                ),
                timeout=4.8,  # 카카오톡 5초 제한 안에 응답
            )
            reply = response.content[0].text

        except asyncio.TimeoutError:
            logger.warning(f"AI 응답 타임아웃 [{user_id}]")
            reply = "죄송해요, 응답이 잠깐 지연됐어요!\n전화로 문의해 주시면 바로 안내해 드릴게요 📞 010-6547-1067"
        except Exception as e:
            logger.error(f"AI 응답 오류: {e}")
            reply = "죄송해요, 잠시 오류가 발생했어요. 전화로 문의해 주세요 📞 010-6547-1067"

        # 대화 기록에 AI 응답 추가
        conversation_history[user_id].append({"role": "assistant", "content": reply})

        return reply