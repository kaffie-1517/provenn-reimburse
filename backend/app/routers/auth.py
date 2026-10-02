import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.deps import Session, current_claims
from app.models import Company, Role, User
from app.schemas import LoginIn, RegisterIn, SessionOut, UserOut
from app.security import DUMMY_HASH, Claims, hash_secret, issue_token, verify_secret

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# No 0/O/1/I so codes survive being read aloud or copied by hand.
_JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _join_code() -> str:
    return "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(8))


def _user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    if user.company:
        out.company_name = user.company.name
        if user.role == Role.COMPANY_ADMIN:
            out.join_code = user.company.join_code
    return out


def _session(user: User) -> SessionOut:
    return SessionOut(token=issue_token(user.id, user.role, user.company_id), user=_user_out(user))


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, session: Session) -> SessionOut:
    email = body.email.lower()
    company: Company | None = None

    if body.role == Role.COMPANY_ADMIN:
        if not body.company_name:
            raise HTTPException(422, "Company name is required to create a workspace")
        company = Company(name=body.company_name.strip(), join_code=_join_code())
        session.add(company)
    elif body.role == Role.EMPLOYEE:
        if not body.join_code:
            raise HTTPException(422, "Ask your company admin for a join code")
        company = await session.scalar(
            select(Company).where(Company.join_code == body.join_code.strip().upper())
        )
        if company is None:
            raise HTTPException(422, "That join code doesn't match any company")

    user = User(
        email=email,
        password_hash=hash_secret(body.password),
        role=body.role,
        company=company,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        msg = str(e.orig)
        if "users_email" in msg:
            raise HTTPException(409, "An account with this email already exists") from e
        if "companies_name" in msg:
            raise HTTPException(409, "A company with this name already exists") from e
        raise
    await session.refresh(user, ["company"])
    return _session(user)


@router.post("/login")
async def login(body: LoginIn, session: Session) -> SessionOut:
    user = await session.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not verify_secret(body.password, user.password_hash if user else DUMMY_HASH) or not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect")
    return _session(user)


@router.get("/me")
async def me(claims: Annotated[Claims, Depends(current_claims)], session: Session) -> UserOut:
    user = await session.get(User, claims.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer exists")
    return _user_out(user)
