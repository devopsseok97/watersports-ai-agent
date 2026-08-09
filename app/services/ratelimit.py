"""요청 출처 판별 + 로그인 무차별 대입 방어.

관리자·운영 화면은 공개 URL에 열려 있고 인증이 비밀번호 하나뿐이다.
시도 제한이 없으면 초당 수십 번 대입이 가능해, 사람이 기억할 만한 길이의
비밀번호는 오래 버티지 못한다. 그 화면 안에는 예약자 이름과 연락처가 있다.
"""
import logging
import time
from collections import deque

from fastapi import Request

logger = logging.getLogger(__name__)

MAX_LOGIN_FAILS = 5           # 출처 하나당 허용 실패 수
MAX_LOGIN_FAILS_GLOBAL = 40   # 화면 하나당 전체 허용 실패 수 (IP 위조 대비)
LOGIN_WINDOW_SEC = 600
_MAX_TRACKED = 2000

_fails: dict[str, deque] = {}
_fails_global: dict[str, deque] = {}


def client_key(request: Request) -> str:
    """요청 출처 식별자.

    request.client.host는 레일웨이 엣지 프록시 IP라 모든 방문자가 한 값으로
    뭉친다. 프록시가 붙여주는 X-Forwarded-For의 첫 항목을 쓴다.

    2026-08-09 실측: 레일웨이 엣지가 이 헤더를 직접 세팅해서, 외부에서 값을
    넣어 보내도 실제 접속 IP로 덮인다(다른 값을 넣은 두 요청이 같은 키로
    집계됨). 다만 이건 우리가 통제하지 못하는 인프라 동작이라, 로그인은
    MAX_LOGIN_FAILS_GLOBAL로 한 번 더 막아 둔다.
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def _prune(q: deque, now: float) -> None:
    while q and now - q[0] > LOGIN_WINDOW_SEC:
        q.popleft()


def login_locked(scope: str, key: str) -> bool:
    now = time.monotonic()

    g = _fails_global.get(scope)
    if g is not None:
        _prune(g, now)
        if len(g) >= MAX_LOGIN_FAILS_GLOBAL:
            return True

    q = _fails.get(f"{scope}|{key}")
    if q is None:
        return False
    _prune(q, now)
    return len(q) >= MAX_LOGIN_FAILS


def record_login_failure(scope: str, key: str) -> None:
    now = time.monotonic()
    full = f"{scope}|{key}"

    q = _fails.get(full)
    if q is None:
        if len(_fails) >= _MAX_TRACKED:
            for k in [k for k, v in _fails.items() if not v or now - v[-1] > LOGIN_WINDOW_SEC]:
                _fails.pop(k, None)
            while len(_fails) >= _MAX_TRACKED:
                _fails.pop(next(iter(_fails)))
        q = _fails[full] = deque()
    _prune(q, now)
    q.append(now)

    g = _fails_global.setdefault(scope, deque())
    _prune(g, now)
    g.append(now)

    if len(q) == MAX_LOGIN_FAILS or len(g) == MAX_LOGIN_FAILS_GLOBAL:
        logger.error(f"로그인 시도 제한 발동 [{scope}] key={key} (연속 실패 누적)")


def record_login_success(scope: str, key: str) -> None:
    _fails.pop(f"{scope}|{key}", None)


def reset() -> None:
    _fails.clear()
    _fails_global.clear()
