import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_DEV_KEY = "tradeiq-development-only-credential-key"


def _fernet() -> Fernet:
    secret = get_settings().credential_encryption_key or _DEV_KEY
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest()))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return None
