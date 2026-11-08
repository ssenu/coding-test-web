"""관리자 세션 쿠키와 참가자 토큰."""
import hashlib
import hmac
import secrets

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import Settings

ADMIN_COOKIE = "admin_session"
ADMIN_MAX_AGE = 12 * 60 * 60


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="admin-session")


def password_ok(settings: Settings, password: str) -> bool:
    return hmac.compare_digest(password.encode("utf-8"), settings.admin_password.encode("utf-8"))


def make_admin_cookie(settings: Settings) -> str:
    return _serializer(settings).dumps({"admin": True})


def check_admin_cookie(settings: Settings, value: str | None) -> bool:
    if not value:
        return False
    try:
        data = _serializer(settings).loads(value, max_age=ADMIN_MAX_AGE)
    except BadSignature:
        return False
    return isinstance(data, dict) and data.get("admin") is True


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
