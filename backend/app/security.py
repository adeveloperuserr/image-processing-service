from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.settings import Settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return password_hash.verify(password, stored_hash)


def create_access_token(user_id: UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def token_subject(token: str, settings: Settings) -> UUID:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return UUID(claims["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Token inválido o vencido.") from error
