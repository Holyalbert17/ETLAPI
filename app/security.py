import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.config import settings

_URL_SECRET = re.compile(r"(://[^:/\s]+:)([^@/\s]+)(@)")
_PREFIX = "enc:v1:"
SECRET_NAMES = {
    "dsn",
    "password",
    "passwd",
    "uri",
    "token",
    "api_key",
    "secret",
    "authorization",
    "connection_string",
}


def _fernet() -> Fernet:
    key = hashlib.sha256(settings.ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(data: dict[str, Any], expires_minutes: int | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise ValueError(f"Token inválido: {exc}") from exc


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_text(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return (
        normalized in SECRET_NAMES
        or normalized.endswith("_password")
        or normalized.endswith("_secret")
        or normalized.endswith("_token")
    )


def encrypt_secrets(config: dict) -> dict:
    encrypted: dict = {}
    for key, value in config.items():
        if isinstance(value, dict):
            encrypted[key] = encrypt_secrets(value)
        elif is_secret_key(key) and isinstance(value, str) and value and not value.startswith(_PREFIX):
            encrypted[key] = _PREFIX + encrypt_text(value)
        else:
            encrypted[key] = value
    return encrypted


def decrypt_secrets(config: dict) -> dict:
    decrypted: dict = {}
    for key, value in config.items():
        if isinstance(value, dict):
            decrypted[key] = decrypt_secrets(value)
        elif isinstance(value, str) and value.startswith(_PREFIX):
            decrypted[key] = decrypt_text(value[len(_PREFIX) :])
        else:
            decrypted[key] = value
    return decrypted


def mask_secrets(config: dict) -> dict:
    masked: dict = {}
    for key, value in config.items():
        if isinstance(value, dict):
            masked[key] = mask_secrets(value)
        elif is_secret_key(key) and value not in (None, ""):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def merge_config(old: dict, new: dict) -> dict:
    """Superpone la config nueva y conserva secretos cuando el cliente reenvía ***."""
    merged = dict(old)
    for key, value in new.items():
        if isinstance(value, dict) and isinstance(old.get(key), dict):
            merged[key] = merge_config(old[key], value)
        elif is_secret_key(key) and value == "***":
            merged[key] = old.get(key)
        else:
            merged[key] = value
    return merged


def redact(text: str | None) -> str:
    if not text:
        return ""
    return _URL_SECRET.sub(r"\1***\3", text)
