"""Passwords, session tokens, and encryption for stored API secrets.

The encryption key is derived from SECRET_KEY (or TOKEN_ENCRYPTION_KEY if
set). Tokens are encrypted before they touch the database and are never
written to logs by this module.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_JWT_ALG = "HS256"
_WEAK_SECRETS = {
    "",
    "change-me",
    "change-me-to-a-random-string",
    "demo-only-not-for-production",
}


def assert_runtime_safety() -> None:
    """Refuse to boot a non-demo server with a known default secret."""
    settings = get_settings()
    if settings.demo_mode:
        return
    if settings.secret_key.strip() in _WEAK_SECRETS or len(settings.secret_key) < 24:
        raise RuntimeError(
            "Refusing to start: set SECRET_KEY to a long random value when DEMO_MODE is false."
        )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> str | None:
    if len(password) < 10:
        return "Use at least 10 characters."
    if len(password.encode("utf-8")) > 72:
        return "Passwords must be 72 bytes or fewer."
    return None


def create_access_token(*, user_id: int, workspace_id: int, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "wid": workspace_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(days=settings.token_ttl_days),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALG)


def decode_access_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        return None


def _fernet() -> Fernet:
    settings = get_settings()
    material = (settings.token_encryption_key or settings.secret_key).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if value is None:
        raise ValueError("nothing to encrypt")
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, TypeError, ValueError) as exc:
        raise ValueError("stored credential could not be decrypted") from exc


def verify_shopify_hmac(params: dict[str, str], secret: str) -> bool:
    """Shopify OAuth callback HMAC (hex SHA-256 of the sorted query string)."""
    received = params.get("hmac", "")
    parts = [f"{k}={v}" for k, v in sorted(params.items()) if k not in {"hmac", "signature"}]
    message = "&".join(parts)
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, received)
