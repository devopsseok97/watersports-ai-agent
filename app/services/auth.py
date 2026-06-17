import hmac
import hashlib
from app.config import settings

SESSION_COOKIE = "asess"
_SALT = b"surffirst2026"


def make_token(password: str) -> str:
    return hmac.new(password.encode(), _SALT, hashlib.sha256).hexdigest()


def verify_session(token: str | None) -> bool:
    password = getattr(settings, "admin_password", "") or ""
    if not password:
        return True
    if not token:
        return False
    return hmac.compare_digest(token, make_token(password))
