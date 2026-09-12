from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class CryptoError(Exception):
    pass


def _fernet() -> Fernet:
    key = (settings.fernet_key or "").encode("utf-8")
    if not key:
        raise CryptoError("Не задан FERNET_KEY")
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise CryptoError("FERNET_KEY имеет неверный формат") from exc


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token_encrypted: str) -> str:
    try:
        return _fernet().decrypt(token_encrypted.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError("Не удалось расшифровать токен. Сохраните его снова.") from exc


def token_hint(token: str) -> str:
    cleaned = token.strip()
    if len(cleaned) < 4:
        return "****"
    return cleaned[-4:]
