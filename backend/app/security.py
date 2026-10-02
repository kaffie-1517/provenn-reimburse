import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import get_settings

_ALG = "HS256"


def hash_secret(plain: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds)).decode()


def verify_secret(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


# A bcrypt hash of a random value, checked when the user doesn't exist so a
# failed login takes the same time either way (no email enumeration by timing).
DUMMY_HASH = hash_secret(secrets.token_hex(16))


@dataclass(frozen=True)
class Claims:
    user_id: uuid.UUID
    role: str
    company_id: uuid.UUID | None


def issue_token(user_id: uuid.UUID, role: str, company_id: uuid.UUID | None) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "cid": str(company_id) if company_id else None,
        "iat": now,
        "exp": now + timedelta(hours=s.jwt_ttl_hours),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=_ALG)


def decode_token(token: str) -> Claims:
    """Raises jwt.PyJWTError on any invalid, expired or malformed token."""
    data = jwt.decode(
        token, get_settings().jwt_secret, algorithms=[_ALG], options={"require": ["exp", "sub"]}
    )
    try:
        return Claims(
            user_id=uuid.UUID(data["sub"]),
            role=data["role"],
            company_id=uuid.UUID(data["cid"]) if data.get("cid") else None,
        )
    except (KeyError, ValueError) as e:
        raise jwt.InvalidTokenError("bad claims") from e


# Partner API keys: "pk_<prefix>.<secret>". The prefix is stored in clear and
# indexed so authentication bcrypt-checks exactly one row.
KEY_PREFIX_LEN = 10


def new_partner_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix, bcrypt_hash_of_secret)."""
    prefix = secrets.token_hex(KEY_PREFIX_LEN // 2)
    secret = secrets.token_urlsafe(24)
    return f"pk_{prefix}.{secret}", prefix, hash_secret(secret)


def split_partner_key(key: str) -> tuple[str, str] | None:
    if not key.startswith("pk_") or "." not in key:
        return None
    prefix, _, secret = key[3:].partition(".")
    if len(prefix) != KEY_PREFIX_LEN or not secret:
        return None
    return prefix, secret
