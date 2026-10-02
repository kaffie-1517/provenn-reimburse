from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import reports
from app.deps import Session, require
from app.models import Role

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["platform admin"],
    dependencies=[Depends(require(Role.PLATFORM_ADMIN))],
)

Days = Annotated[int, Query(ge=1, le=365, description="Reporting window in days")]


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


@router.get("/partners")
async def partners(session: Session, days: Days = 30) -> dict:
    since = _since(days)
    return {
        "window_days": days,
        "partners": await reports.partner_usage(session, since),
        # Invoices issued by provider accounts in the portal, not via a partner.
        "direct": await reports.direct_provider_usage(session, since),
    }


@router.get("/companies")
async def companies(session: Session, days: Days = 30) -> dict:
    return {"window_days": days, "companies": await reports.company_usage(session, _since(days))}
