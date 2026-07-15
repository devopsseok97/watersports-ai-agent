import time
import logging
from datetime import datetime, timedelta, timezone

import anthropic
from app.config import settings
from app.services.alerts import FailureAlarm
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

MODEL = "claude-haiku-4-5-20251001"  # 빠르고 저렴. 캐시 워밍과 반드시 동일 모델 사용

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
        await _warm_client.messages.create(
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
        await _warm_alarm.ok()
    except Exception as e:
        logger.warning(f"프롬프트 캐시 워밍 실패({_warm_alarm.fail_count + 1}연속): {e}")
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

★ URL(스마트스토어 링크)은 반드시 완전한 형태로 출력하세요. 중간에 잘리면 손님이 접속 불가.
★ 링크를 붙일 때는 마무리 리뷰 멘트가 잘려도 링크 자체는 절대 자르지 마세요.

[답변 형식]
- 카카오톡은 마크다운 미지원. 별표(**), #, 백틱 등 절대 금지 (그대로 보임).
- 강조는 이모지 라벨 + 줄바꿈. 항목은 한 줄에 하나 (📍 장소 / ⏰ 시간 / 💰 비용 / 👕 준비물).
- 문단 사이 빈 줄. 인사·마무리는 짧고 친근하게, 이모지 가볍게.

[답변 예시 - 형식만 참고. 날짜 옆 요일은 반드시 [날짜-요일 달력]에서 그대로 읽어 채우세요]
안녕하세요! 서퍼스트입니다 🏄

7월 N일(달력의 요일) 선셋카약 38자리 남음 / 선셋패들보드 예약 가능
7월 N일(달력의 요일) 전 종목 예약 가능
7월 N일(화) 휴무 😥 ← 달력에 '휴무'로 표시된 날짜만

💰 선셋카약·패들보드 18:30 / 1인 3만원~5만원

https://smartstore.naver.com/fourseason_1/products/8356965224
이용 후 리뷰 남겨주시면 감사해요 😊

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
1. 잔여석 안내 (현황에 없는 날짜/종목 = 예약 가능 → "예약 가능합니다". 절대 전화 유도 금지!)
2. 요금·시간 1줄
3. 결제 링크 즉시 제공
★ "선셋"만 언급 → 종목 묻지 말고 패들보드/카약 두 링크 모두 제공.
★ 날짜 여러 개 문의 → 손님이 직접 고르니 링크만 제공.

[휴무일과 요일 - 매우 중요]
화요일 휴무. 요일을 절대 직접 계산·추측하지 마세요.
날짜의 요일은 반드시 아래 dynamic 블록의 [날짜-요일 달력]에서 그대로 읽어 쓰세요.
손님이 말한 요일이 달력과 다르면 달력이 정답입니다. 달력 기준으로 부드럽게 안내하세요.
달력에 없는 먼 날짜는 요일을 언급하지 말고 날짜만 말하세요.

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

[주의사항]
- 모르는 정보: "정확한 내용은 전화로 문의해 주세요 📞 {shop['contact']}".
- 잔여석 0석: "해당 시간에는 잔여석이 없습니다 😥\n다른 시간대나 날짜로 변경 원하시거나 추가 문의는 📞 010-6547-1067" (링크 제공 금지).
- 욕설·광고·비상업 대화는 정중히 거절.
- 예약 확정은 직접 하지 말고 "사장님 확인 후 안내 예정"으로 답하세요.
"""


class AgentService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

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

        try:
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model=MODEL,
                    max_tokens=max_tokens,  # 콜백 모드: 넉넉히(400+), 동기 모드: 230
                    system=system_blocks,
                    messages=history,
                    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
                ),
                timeout=timeout_sec,  # 콜백 모드: 50s, 동기 모드: 4.2s
            )
            reply = response.content[0].text

        except asyncio.TimeoutError:
            logger.warning(f"AI 응답 타임아웃 [{user_id}]")
            reply = "죄송해요, 응답이 잠깐 지연됐어요!\n전화로 문의해 주시면 바로 안내해 드릴게요 📞 010-6547-1067"
        except Exception as e:
            logger.error(f"AI 응답 오류: {e}")
            reply = "죄송해요, 잠시 오류가 발생했어요. 전화로 문의해 주세요 📞 010-6547-1067"

        # 대화 기록에 AI 응답 추가 후 최근 N턴만 보관 (무한 증가 방지)
        conversation_history[user_id].append({"role": "assistant", "content": reply})
        if len(conversation_history[user_id]) > MAX_HISTORY * 2:
            conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY * 2:]

        return reply