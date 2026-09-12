import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

_serializer = URLSafeTimedSerializer(settings.session_secret, salt="portfel-session")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def parse_session_token(token: str) -> int | None:
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None
    user_id = data.get("uid")
    return int(user_id) if user_id is not None else None
