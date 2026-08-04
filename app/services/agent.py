import time
import logging
from datetime import datetime, timedelta, timezone

import anthropic
from app.config import settings
from app.services.alerts import FailureAlarm
from app.services.api_health import anthropic_circuit, classify_fatal
from app.services.usage import tracker as usage_tracker
from app.services.weather import get_operation_status
from app.services.availability import build_availability_text, today_str

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def build_calendar_text(days: int = 21) -> str:
    """앞으로 N일 날짜→요일 달력 (휴무 표기 포함).

    LLM은 날짜에서 요일을 직접 계산하면 자주 틀린다 (7/17(금)을 (목)이라고
    우기며 손님과 언쟁한 사고). 서버가 정확히 계산해 프롬프트에 넣어주고
    모델은 읽기만 하게 한다.
    """
    now = datetime.now(KST)
    parts = []
    for i in range(days):
        d = now + timedelta(days=i)
        wd = _WEEKDAY_KO[d.weekday()]
        parts.append(f"{d.month}/{d.day}({wd}{'·휴무' if d.weekday() == 1 else ''})")
    return " ".join(parts)

MODEL = "claude-haiku-4-5-20251001"  # 주 모델: 빠르고 저렴. 캐시 워밍과 반드시 동일 모델 사용
# 폴백 모델: 주 모델이 일시 오류(529 오버로드 등)를 뱉을 때만 사용. 별도 용량 풀이라
# 같은 순간 오버로드를 피할 확률이 높다. Haiku보다 느리지만 폴백 경로는 드물다.
FALLBACK_MODEL = "claude-sonnet-5"

# 날씨·잔여석 인메모리 캐시 (Railway 재시작 시 초기화)
# ── 중요: 외부 API(KMA/Supabase) 호출은 백그라운드 루프(main.py)에서만 수행한다.
#         카카오 요청 경로에서는 절대 await 하지 않고 캐시 값만 즉시 읽는다.
#         (요청당 추가 지연 ≈ 0초 → 5초 카카오 타임아웃 안전)
_cache: dict = {}
_WEATHER_TTL = 1800  # 30분 (참고용)
_AVAIL_TTL   = 60    # 1분 (참고용)


# ── 백그라운드 갱신 (main.py lifespan 루프에서 호출) ──────────────────────────

# 30분 주기 → 3회 = 1.5시간 안에 감지
_weather_alarm = FailureAlarm(
    "날씨 갱신(KMA API)", threshold=3,
    hint="챗봇이 낡은 날씨 정보로 안내 중입니다. KMA_API_KEY 유효기간을 확인하세요.",
)
# 1분 주기 → 3회 = 3분 안에 감지
_avail_alarm = FailureAlarm(
    "잔여석 캐시 갱신(Supabase)", threshold=3,
    hint="챗봇이 낡은 잔여석 정보로 답하는 중입니다. Supabase 상태를 확인하세요.",
)


async def refresh_weather_cache() -> None:
    """날씨/운영상태 캐시 갱신. 실패해도 직전 값 유지."""
    try:
        val = await get_operation_status()
        _cache["weather"] = (time.monotonic(), val)
        await _weather_alarm.ok()
    except Exception as e:
        logger.warning(f"날씨 캐시 갱신 실패(직전 값 유지): {e}")
        await _weather_alarm.fail(e)


async def refresh_availability_cache() -> None:
    """잔여석 캐시 갱신. 실패해도 직전 값 유지."""
    try:
        val = await build_availability_text()
        _cache["avail"] = (time.monotonic(), val)
        await _avail_alarm.ok()
    except Exception as e:
        logger.warning(f"잔여석 캐시 갱신 실패(직전 값 유지): {e}")
        await _avail_alarm.fail(e)


_warm_client: "anthropic.AsyncAnthropic | None" = None

# 워밍은 4분 주기 → 2회 = 약 8분 안에 감지. 연속 실패는 API 접근 불가
# (크레딧 소진·키 만료·모델 오류)의 조기 신호다.
_warm_alarm = FailureAlarm(
    "카톡 AI 응답(Anthropic API)", threshold=2,
    hint="지금 손님 문의가 오면 오류 폴백이 나갑니다. "
         "크레딧 소진이면 console.anthropic.com → Plans & Billing에서 충전하세요.",
)


async def warm_anthropic_cache() -> None:
    """Anthropic 프롬프트 캐시(TTL 5분) 워밍.

    5분 넘게 대화가 없으면 캐시가 식어 첫 메시지가 3.5초 타임아웃에 걸리고
    두 번째 메시지부터 정상 응답하는 문제가 있었다. 4분마다 max_tokens=1짜리
    초소형 요청으로 캐시를 데워두면 첫 메시지도 항상 캐시 히트 → 즉시 응답.
    get_reply와 동일한 정적 system 블록·모델을 써야 같은 캐시를 공유한다.
    """
    global _warm_client
    try:
        if _warm_client is None:
            _warm_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        warm_resp = await _warm_client.messages.create(
            model=MODEL,
            max_tokens=1,
            system=[
                {
                    "type": "text",
                    "text": build_system_prompt(),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": "."}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )
        # 워밍은 하루 360회 돈다. 캐시가 실제로 만들어지는지 여기서 반드시 확인해야
        # 한다 — 안 만들어지면 이 루프는 매달 수십 달러를 아무 효과 없이 태운다.
        usage_tracker.record(MODEL, getattr(warm_resp, "usage", None), "warm")
        # 워밍 성공 = API 정상. 회로가 열려 있었다면 여기서만 복구된다
        # (요청 경로에서 복구를 탐지하면 손님이 그 대기시간을 부담하게 되므로).
        await anthropic_circuit.close()
        await _warm_alarm.ok()
    except Exception as e:
        logger.warning(f"프롬프트 캐시 워밍 실패({_warm_alarm.fail_count + 1}연속): {e}")
        fatal = classify_fatal(e)
        if fatal:
            # 크레딧 소진·키 만료 등 재시도 무의미 오류 → 회로 개방 + 전용 경보(30분 주기)
            await anthropic_circuit.trip(fatal[0], fatal[1], e)
        else:
            await _warm_alarm.fail(e)


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

_PRICE_KEYWORDS = ("가격", "요금", "얼마", "비용", "금액", "price", "cost", "how much")
_PHOTO_KEYWORDS = ("사진", "포토", "photo", "picture", "이미지")
_BOOKING_QUERY_KEYWORDS = (
    "예약 가능", "예약이 가능", "예약되나요", "예약 되나요",
    "예약하고 싶", "예약 하고 싶", "신청하고 싶", "신청 하고 싶",
    "예약 문의", "예약문의",
)
_CANCEL_KEYWORDS = ("취소", "환불", "refund", "cancel")


def _static_fallback(message: str, shop_key: str = "default") -> str | None:
    """AI 호출이 재시도까지 실패했을 때 단골 질문은 서버가 직접 답한다.

    2026-07-16 가격 문의·2026-07-19 사진 수령 문의·2026-07-23 예약 문의가
    Anthropic 일시 오류로 오류 폴백을 받은 사고 재발 방지.
    """
    shop = SHOP_CONFIG.get(shop_key, SHOP_CONFIG["default"])
    m = message.lower()
    if any(k in m for k in _PRICE_KEYWORDS):
        # 물어본 종목만 골라 짧게 답한다. 종목 언급이 없을 때만 전체 안내.
        prog_map = {
            "패들보드": "패들보드", "패들": "패들보드",
            "카약": "카약",
            "윈드": "윈드서핑",
            "전동": "전동e포일",
            "펌핑": "펌핑포일",
            "e포일": "E포일", "이포일": "E포일", "포일": "E포일",
        }
        wanted = {v for k, v in prog_map.items() if k in m}
        # "전동" 매칭 시 "포일"의 E포일 오매칭 제거
        if "전동" in m:
            wanted.discard("E포일")
        items = {k: v for k, v in shop["prices"].items()
                 if not wanted or any(w in k for w in wanted)}
        # 종목명에서 괄호 설명 제거해 한 줄로 간결하게
        lines = "\n".join(f"💰 {k.split(' (')[0]}: {v}" for k, v in items.items())
        return f"{lines}\n\n예약: 네이버 스마트스토어 또는 전화 {shop['contact']} 😊"
    if any(k in m for k in _PHOTO_KEYWORDS):
        return (
            f"사진은 사장님께서 직접 챙겨드리고 있어요 📸\n"
            f"사장님께 연락 주시면 바로 안내받으실 수 있습니다 📞 {shop['contact']}"
        )
    if any(k in message for k in _BOOKING_QUERY_KEYWORDS):
        links = shop.get("smartstore_links", {})
        paddle_link = links.get("패들보드/카약", "")
        return (
            "네, 예약 가능합니다! 🏄\n"
            f"아래 링크에서 바로 예약하세요 👉 {paddle_link}\n"
            f"(윈드서핑·E포일·펌핑포일은 전화 문의 📞 {shop['contact']})"
        )
    if any(k in message.lower() for k in _CANCEL_KEYWORDS):
        return (
            f"취소는 가능하지만 환불은 어려운 점 양해 부탁드립니다 🙏\n"
            f"취소 문의는 전화로 연락 주세요 📞 {shop['contact']}"
        )
    return None


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
매우 간결하게 답하세요 (인사 1줄 + 정보 3~5줄 + 링크). 24시간 응답 가능하며, 시간과 무관하게 답변하세요.
"내일", "이번 주말" 등 상대 표현은 아래 오늘 날짜와 [날짜-요일 달력] 기준으로 해석하세요.

[언어]
손님이 쓴 언어로 답하세요. 영어로 물으면 영어로, 일본어면 일본어로, 중국어면 중국어로.
외국어 답변에도 가격(₩30,000 형식)·시간·링크·전화번호는 동일하게 안내하세요.
휴무 안내 예: "We are closed on Tuesdays."

[외국어 응답 예시 - 영어 문의 "How much is paddleboarding?"]
Hello! This is Surf1st 🏄
💰 Paddleboard (2-hour session): ₩30,000 rental / ₩50,000 with lesson
⏰ Day sessions: 10:00 / 13:00 / 15:00 · Sunset session: 18:30
We are closed on Tuesdays.

https://smartstore.naver.com/fourseason_1/products/8356965224
Please leave a review after your visit 😊

[외국어 응답 예시 - 일본어 문의 「カヤックの予約はできますか？」]
こんにちは！Surf1stです 🏄
はい、カヤックのご予約が可能です！
💰 お一人様 ₩30,000（2時間体験、2人乗り1艇が基準）
⏰ 開始時間: 10:00 / 13:00 / 15:00 · サンセットは18:30
火曜日は定休日です。

https://smartstore.naver.com/fourseason_1/products/8356965224
ご利用後のレビューもお願いします 😊

[외국어 응답 예시 - 중국어 문의 "桨板多少钱？"]
您好！这里是Surf1st 🏄
💰 桨板（2小时体验）：租赁 ₩30,000 / 含教学 ₩50,000
⏰ 白天场 10:00 / 13:00 / 15:00 · 日落场 18:30
周二休息。

https://smartstore.naver.com/fourseason_1/products/8356965224
欢迎体验后留下评价 😊

★ URL(스마트스토어 링크)은 반드시 완전한 형태로 출력하세요. 중간에 잘리면 손님이 접속 불가.
★ 링크를 붙일 때는 마무리 리뷰 멘트가 잘려도 링크 자체는 절대 자르지 마세요.

[답변 형식]
- 카카오톡은 마크다운 미지원. 별표(**), #, 백틱 등 절대 금지 (그대로 보임).
- 강조는 이모지 라벨 + 줄바꿈. 항목은 한 줄에 하나 (📍 장소 / ⏰ 시간 / 💰 비용 / 👕 준비물).
- 문단 사이 빈 줄. 인사·마무리는 짧고 친근하게, 이모지 가볍게.

[답변 예시 - 손님이 "7월 N일 선셋패들보드 2인 돼요?"라고 물었을 때]
안녕하세요! 서퍼스트입니다 🏄
7월 N일(달력의 요일) 선셋패들보드 예약 가능합니다!
💰 렌탈 3만원 / 강습포함 5만원 · 18:30 시작

https://smartstore.naver.com/fourseason_1/products/8356965224
이용 후 리뷰 남겨주시면 감사해요 😊
(→ 다른 날짜·종목 잔여석은 절대 나열하지 않는다)

[업체 정보]
- 종목: {', '.join(shop['sports'])}
- 운영시간:{shop['hours']}
- 위치: {shop['location']}
- 문의전화: {shop['contact']}
- 초보자 가능 / 최소 {shop['min_age']}세

[요금]
{prices_text}

[예약 방법]
{shop['reservation_method']}

[준비물 및 안내사항]
{shop.get('preparation', '')}

[네이버 스마트스토어 결제 링크]
{smartstore_text}
  - E포일/펌핑포일: 링크 없음 → 전화 예약 (010-6547-1067)

[결제 링크 안내 규칙]
- 종목+날짜 언급 (예: "패들보드 7/4", "카약 이번 주말") → 잔여석 안내 후 즉시 링크. 추가 질문 금지.
- 종목 관심·가격·시간 문의 → 안내 후 마지막에 링크.
- "결제/예약/신청" 등 의향 표현 → 즉시 링크.
- 여러 종목이면 각 링크 모두. 스냅사진 문의 시 스냅 링크.
- E포일/펌핑포일 관심 시 "전화로 예약 가능합니다 📞 010-6547-1067".
- 리뷰 부탁 한 줄만 자연스럽게 (예: "이용 후 리뷰도 남겨주시면 감사해요 😊").

[날짜+종목 응답 흐름 - 필수]
1. 손님이 물은 날짜·종목만 "가능/불가"로 딱 답하세요. (현황에 없으면 = 예약 가능 → "예약 가능합니다". 절대 전화 유도 금지!)
2. 요금·시간 1줄
3. 결제 링크 즉시 제공
★ 절대 [예약 가능 현황]의 다른 날짜·다른 종목 잔여석을 나열하지 마세요. 손님이 안 물어본 정보는 TMI입니다.
★ 잔여 좌석 숫자(예: "38자리 남음")는 말하지 마세요. "예약 가능합니다"로 충분합니다. (0석일 때만 마감 안내)
★ "선셋"만 언급 → 종목 묻지 말고 패들보드/카약 두 링크 모두 제공.
★ 날짜 여러 개 문의 → 손님이 직접 고르니 링크만 제공.

[휴무일과 요일 - 매우 중요]
화요일 휴무. 요일을 절대 직접 계산·추측하지 마세요.
날짜의 요일은 반드시 아래 dynamic 블록의 [날짜-요일 달력]에서 그대로 읽어 쓰세요.
손님이 말한 요일이 달력과 다르면 달력이 정답입니다. 달력 기준으로 부드럽게 안내하세요.
달력에 없는 먼 날짜는 요일을 언급하지 말고 날짜만 말하세요.

[상대 날짜 해석 예시 - 오늘이 7/1(수)라고 가정할 때]
- "내일" → 7/2. 달력에서 7/2의 요일을 읽어 그대로 쓴다.
- "모레" → 7/3.
- "이번 주말" → 달력에서 가장 가까운 토·일을 찾아 그 날짜로 답한다.
- "다음주 화요일" → 달력에서 다음 주의 화요일을 찾는다. 화요일은 휴무이므로
  "화요일은 휴무예요 😊 수요일이나 다른 요일은 어떠세요?"처럼 대안을 제안한다.
- "이번 달 말" → 손님이 날짜를 특정하도록 "혹시 날짜 정해지셨을까요?" 한 번만 확인.
- 손님이 "금요일에 가려고요"처럼 요일만 말하면 → 달력에서 가장 가까운 그 요일 날짜로
  해석하고, 답변에 날짜를 함께 표기해 오해를 방지한다 (예: "7/3(금) 예약 가능합니다!").

[예약 가능 현황 읽는 법]
- dynamic 블록의 [예약 가능 현황]에는 "마감된 타임만" 표시된다.
- 손님이 물은 날짜·종목·시간이 현황에 없으면 = 예약 가능. 바로 "예약 가능합니다!"
- 현황에 마감으로 있으면 = 그 타임만 마감. 같은 날 다른 시간대나 다른 날짜를 제안한다.
- 현황이 비어 있으면 = 전 타임 예약 가능.

[카약 특이사항]
2인 1카약 기준, 요금은 인당 3만원. 예약은 인당 1개.
인원/예약 수 문의 시 답변:
"카약은 2인 1카약이고 요금은 인당이라, 2명이시면 예약 2개 해주시면 됩니다!
혼자서 한 개 카약 타셔도 되고, 가격도 똑같아요 😊
다만 2인용 카약이라 가급적 2명이서 타시는 걸 추천드려요.
바람이 거세지면 혼자 앞으로 나아가기가 쉽지 않거든요!"

[취소·환불]
취소 가능, 환불 불가. 문의 시:
"취소는 가능하지만 환불은 어려운 점 양해 부탁드립니다 🙏
취소 문의는 전화로 연락 주세요 📞 010-6547-1067"

[주차·오시는 길]
뚝섬한강공원 제1주차장(유료). 클럽은 맞은편 1번 건물.
"뚝섬한강공원 제1주차장에 주차하시면 됩니다 🅿️
저희 클럽은 제1주차장 바로 맞은편 1번 건물이에요!
📍 서울 광진구 강변북로 2326 서울윈드서핑장 1번 서퍼스트"

[애견동반]
카약·패들보드 모두 가능.
"네, 카약과 패들보드 모두 애견동반 가능합니다! 🐶
함께 즐거운 시간 보내러 오세요 😊"

[사진 수령]
촬영된 사진을 받는 방법 문의(카톡으로 주는지, 언제·어떻게 받는지 등) 시:
"사진은 사장님께서 직접 챙겨드리고 있어요 📸
사장님께 연락 주시면 바로 안내받으실 수 있습니다 📞 {shop['contact']}"

[포일 3종 구분 - 손님이 "포일"이라고만 하면 헷갈리기 쉬움]
- 전동e포일: 1시간 체험, 시간 협의 후 예약. 렌탈 8만원 / 강습포함 15만원.
  스마트스토어 링크로 결제 가능.
- E포일: 3시간 체험, 정원 2명, 09:00/13:00 시작. 렌탈 8만원 / 강습포함 15만원.
  링크 없음 → 전화 예약 (010-6547-1067).
- 펌핑포일: 2시간 체험, 시간 협의 후 예약. 렌탈 7만원 / 강습포함 10만원.
  링크 없음 → 전화 예약 (010-6547-1067).
- 손님이 그냥 "포일 타고 싶어요"라고 하면 어떤 포일인지 한 번만 확인한다
  (예: "전동e포일과 E포일, 펌핑포일이 있어요! 어떤 체험을 원하세요?").

[스냅사진]
- 스냅사진 촬영 상품 문의 시 스냅사진 스마트스토어 링크를 안내한다.
- 이미 촬영된 사진을 받는 방법 문의는 아래 [사진 수령] 안내를 따른다.

[응대 세부 원칙]
- 첫 메시지에는 "안녕하세요! 서퍼스트입니다 🏄"로 인사하되, 대화가 이어지는 중이면
  인사를 반복하지 않고 바로 본론으로 답한다.
- 손님이 이미 말한 정보(날짜·인원·종목)를 다시 묻지 않는다. 짧은 문장(예: "패들 내일 2명")도
  최대한 해석해 바로 답한다.
- 같은 질문이 반복되어도 처음처럼 친절하게 같은 내용을 안내한다.
- 확실하지 않은 정보는 절대 지어내지 않는다. 모르면 전화 안내로 연결한다.
- 한 답변 안에서 같은 링크를 두 번 반복하지 않는다.
- 가격 문의에 종목이 특정되면 그 종목만 답하고, 종목 언급이 없을 때만 전체 요금을 안내한다.
- 답변은 항상 완결된 문장으로 끝낸다. 링크가 포함되면 링크 뒤에 짧은 마무리 한 줄.

[주의사항]
- 모르는 정보: "정확한 내용은 전화로 문의해 주세요 📞 {shop['contact']}".
- 잔여석 0석: "해당 시간에는 잔여석이 없습니다 😥\n다른 시간대나 날짜로 변경 원하시거나 추가 문의는 📞 010-6547-1067" (링크 제공 금지).
- 욕설·광고·비상업 대화는 정중히 거절.
- 예약 확정은 직접 하지 말고 "사장님 확인 후 안내 예정"으로 답하세요.
"""


# LLM 분류 실패 시 폴백용 (과거 단독 판정 방식 — 표현 변형을 놓쳐 LLM 분류로 대체됨)
BOOKING_KEYWORDS = ["예약", "신청", "하고 싶어", "가능한가요", "얼마예요", "결제"]

_INTENT_PROMPT = (
    "손님 메시지가 예약 의향(예약·구매·일정/잔여석 확인·가격 문의 등 예약으로 "
    "이어질 수 있는 의도)을 담고 있으면 Y, 아니면(단순 인사·감사·잡담) N.\n"
    "Y 또는 N 한 글자만 출력하세요."
)


class AgentService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def classify_booking_intent(self, message: str) -> bool:
        """예약 의향 분류. 백그라운드 전용 — 카톡 응답 경로에서 호출 금지.

        실패하거나 출력이 Y/N이 아니면 키워드 매칭으로 폴백.
        """
        import asyncio

        # 회로 개방 중에는 호출해봐야 실패 로그만 쌓인다 → 바로 키워드 폴백.
        if anthropic_circuit.is_open:
            return any(kw in message for kw in BOOKING_KEYWORDS)

        try:
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model=MODEL,
                    max_tokens=2,
                    system=_INTENT_PROMPT,
                    messages=[{"role": "user", "content": message[:500]}],
                ),
                timeout=10.0,
            )
            usage_tracker.record(MODEL, getattr(response, "usage", None), "intent")
            verdict = response.content[0].text.strip().upper()
            if verdict.startswith("Y"):
                return True
            if verdict.startswith("N"):
                return False
            logger.warning(f"의도 분류 출력 이상('{verdict}') — 키워드 폴백")
        except Exception as e:
            logger.warning(f"의도 분류 실패({e}) — 키워드 폴백")
        return any(kw in message for kw in BOOKING_KEYWORDS)

    async def get_reply(
        self,
        user_id: str,
        message: str,
        shop_key: str = "default",
        *,
        max_tokens: int = 230,
        timeout_sec: float = 4.2,
    ) -> str:
        import asyncio

        # 날씨·잔여석: 백그라운드가 미리 채워둔 캐시만 즉시 읽음 (외부 호출 없음 → 지연 0)
        weather_status = get_cached_weather()
        availability_status = get_cached_availability()

        # 대화 기록 초기화 (dict 삽입 순서 = 최근 사용 순서로 유지해 LRU 퇴출)
        if user_id not in conversation_history:
            # 유저 수 한도 초과 시 가장 오래 안 쓴 유저부터 제거
            if len(conversation_history) >= MAX_USERS:
                oldest_keys = list(conversation_history.keys())[:MAX_USERS // 10]
                for k in oldest_keys:
                    del conversation_history[k]
            conversation_history[user_id] = []
        else:
            conversation_history[user_id] = conversation_history.pop(user_id)

        # 대화 기록에 사용자 메시지 추가
        conversation_history[user_id].append({"role": "user", "content": message})

        # 최근 N턴만 유지
        history = conversation_history[user_id][-MAX_HISTORY * 2:]

        # 시스템 프롬프트: 정적 블록(캐시) + 동적 블록(날짜·날씨·잔여석)
        now_kst = datetime.now(KST)
        dynamic_part = (
            f"오늘 날짜: {today_str()} ({_WEEKDAY_KO[now_kst.weekday()]}요일, KST)\n\n"
            f"[날짜-요일 달력 (오늘부터 3주) - 요일은 반드시 여기서 그대로 읽을 것, 직접 계산 금지]\n"
            f"{build_calendar_text()}\n\n"
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

        # API가 즉시 예외를 던지는 일시 오류(수백 ms, 주로 529 오버로드)에 대응해
        # deadline 안에서 여러 번 재시도한다. 매 재시도는 (1) 점점 길어지는 backoff로
        # 같은 오버로드 순간을 피하고 (2) 주 모델 ↔ 폴백 모델(Sonnet 5, 별도 용량 풀)을
        # 번갈아 써 모델 풀 단위 오버로드를 우회한다.
        # 재시도 개수는 남은 시간이 결정한다:
        #   - 동기 모드(4.2s): 자연히 앞 1~2개만 실행 → 지연 없음
        #   - 콜백 모드(50s): 전체 실행 → 일시 오버로드 버스트를 거의 흡수
        # 타임아웃은 시간이 소진된 것이므로 재시도하지 않는다.
        deadline = time.monotonic() + timeout_sec
        reply = None
        timed_out = False
        # 오버로드(529)는 수 초~수십 초 지속될 수 있으므로, 콜백 모드의 50초 예산을
        # 넓게 써서 t=0~30초에 걸쳐 재시도한다. 짧은 버스트뿐 아니라 20~30초짜리
        # 오버로드도 흡수 → 손님이 오류 대신 정상 답변을 받을 확률을 크게 높인다.
        attempts = [
            (MODEL, 0.0),            # 1) 주 모델 즉시
            (FALLBACK_MODEL, 0.5),   # 2) 폴백 모델 — 동기 모드는 보통 여기까지
            (MODEL, 1.5),            # 3) 주 모델 재시도
            (FALLBACK_MODEL, 3.0),   # 4) 폴백 모델 재시도
            (MODEL, 5.0),            # 5~) 이하 콜백 모드(50s)에서만 도달
            (FALLBACK_MODEL, 8.0),
            (MODEL, 12.0),
        ]
        # 회로가 열려 있으면(크레딧 소진 등 확정 장애) 호출 자체를 건너뛴다.
        # 어차피 7회 전멸할 요청에 손님을 30초 기다리게 하지 않는다 → 즉시 정적 폴백.
        if anthropic_circuit.is_open:
            logger.warning(
                f"Anthropic 회로 개방 상태({anthropic_circuit.kind}) — "
                f"호출 생략하고 즉시 폴백 [{user_id}]"
            )
            attempts = []

        for attempt, (model, backoff) in enumerate(attempts, start=1):
            if backoff:
                await asyncio.sleep(backoff)
            remaining = deadline - time.monotonic()
            if remaining < 0.5:
                break
            try:
                response = await asyncio.wait_for(
                    self.client.messages.create(
                        model=model,
                        max_tokens=max_tokens,  # 콜백 모드: 넉넉히(400+), 동기 모드: 230
                        system=system_blocks,
                        messages=history,
                        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
                    ),
                    timeout=remaining,  # 콜백 모드: 50s, 동기 모드: 4.2s (재시도 시 잔여분)
                )
                usage_tracker.record(model, getattr(response, "usage", None), "reply")
                reply = response.content[0].text
                break
            except asyncio.TimeoutError:
                logger.warning(f"AI 응답 타임아웃 [{user_id}] (모델 {model})")
                timed_out = True
                break
            except Exception as e:
                logger.error(f"AI 응답 오류(시도 {attempt}, 모델 {model}): {e}")
                fatal = classify_fatal(e)
                if fatal:
                    # 재시도해도 100% 실패 → 남은 시도를 버리고 회로를 열어
                    # 이후 손님들은 대기 없이 폴백을 받는다. 워밍 루프보다 먼저
                    # 손님 요청이 장애를 감지하는 경우가 있어 여기서도 회로를 연다.
                    await anthropic_circuit.trip(fatal[0], fatal[1], e)
                    break

        if reply is None:
            # 재시도까지 실패 → 단골 질문(가격 등)은 서버가 직접 답변
            reply = _static_fallback(message, shop_key)
        if reply is None:
            # 오류처럼 보이는 문구는 손님을 불안하게 한다 → 자연스러운 안내로 통일.
            reply = (
                "안녕하세요! 서퍼스트입니다 🏄\n"
                "지금 문의가 많아 답변이 조금 늦어지고 있어요.\n"
                "빠른 안내는 전화 주시면 바로 도와드릴게요 📞 010-6547-1067"
            )

        # 대화 기록에 AI 응답 추가 후 최근 N턴만 보관 (무한 증가 방지)
        conversation_history[user_id].append({"role": "assistant", "content": reply})
        if len(conversation_history[user_id]) > MAX_HISTORY * 2:
            conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY * 2:]

        return reply