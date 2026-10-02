import uuid
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Partner, Role
from app.security import Claims, decode_token, split_partner_key, verify_secret

Session = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


def current_claims(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Claims:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        return decode_token(creds.credentials)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid") from e


def require(*roles: Role) -> Callable[..., Claims]:
    """Dependency factory: the caller must hold one of `roles`."""
    allowed = {r.value for r in roles}

    def guard(claims: Annotated[Claims, Depends(current_claims)]) -> Claims:
        if claims.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for your role")
        return claims

    return guard


def tenant_id(claims: Claims) -> uuid.UUID:
    """The caller's company. Always from the token, never from the request."""
    if claims.company_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No company on this account")
    return claims.company_id


async def current_partner(
    session: Session,
    x_partner_key: Annotated[str | None, Header()] = None,
) -> Partner:
    parts = split_partner_key(x_partner_key or "")
    if parts is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or malformed X-Partner-Key")
    prefix, secret = parts
    partner = await session.scalar(select(Partner).where(Partner.key_prefix == prefix))
    if partner is None or not verify_secret(secret, partner.key_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid partner key")
    return partner
