import hmac
import hashlib
import logging
import time
from app.config import settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "asess"
SESSION_TTL_SEC = 30 * 24 * 3600  # remember 쿠키 수명(30일)과 동일

_pw_missing_warned = False


def _salt() -> bytes:
    return (getattr(settings, "session_salt", "") or "surffirst2026").encode()


def make_token(password: str) -> str:
    ts = str(int(time.time()))
    msg = _salt() + b"|admin|" + ts.encode()
    sig = hmac.new(password.encode(), msg, hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def verify_session(token: str | None) -> bool:
    global _pw_missing_warned
    password = getattr(settings, "admin_password", "") or ""
    if not password:
        # fail-closed: 비밀번호 미설정 시 통과가 아니라 차단
        if not _pw_missing_warned:
            logger.error("ADMIN_PASSWORD 미설정 — 관리자 페이지 접근을 차단합니다 (fail-closed)")
            _pw_missing_warned = True
        return False
    if not token or "." not in token:
        return False
    ts, _, sig = token.partition(".")
    if not ts.isdigit() or time.time() - int(ts) > SESSION_TTL_SEC:
        return False
    msg = _salt() + b"|admin|" + ts.encode()
    expected = hmac.new(password.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)
