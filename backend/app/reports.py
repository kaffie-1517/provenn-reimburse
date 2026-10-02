"""Cross-tenant usage reports for platform admins.

These are the only queries in the codebase that read across companies, so
they live here and are reachable only through the platform_admin routes.
"""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Invoices and billing are aggregated in separate subqueries so the two joins
# can't multiply each other's rows.
_PARTNERS = text(
    """
    SELECT p.id, p.name, p.created_at,
           COALESCE(inv.n, 0)       AS invoices_issued,
           COALESCE(bill.n, 0)      AS downloads,
           COALESCE(bill.cents, 0)::bigint AS billed_cents
      FROM partners p
      LEFT JOIN (SELECT partner_id, count(*) AS n
                   FROM invoices WHERE created_at >= :since
                  GROUP BY partner_id) inv ON inv.partner_id = p.id
      LEFT JOIN (SELECT i.partner_id, count(*) AS n, sum(b.amount_cents) AS cents
                   FROM billing_events b JOIN invoices i ON i.id = b.invoice_id
                  WHERE b.billed_at >= :since
                  GROUP BY i.partner_id) bill ON bill.partner_id = p.id
     ORDER BY invoices_issued DESC, p.name
    """
)

_COMPANIES = text(
    """
    SELECT c.id, c.name, c.plan, c.created_at,
           (SELECT count(*) FROM users u WHERE u.company_id = c.id) AS members,
           count(v.id)                                              AS verifications,
           count(v.id) FILTER (WHERE v.result = 'match')            AS matches,
           count(v.id) FILTER (WHERE v.result = 'mismatch')         AS mismatches,
           count(v.id) FILTER (WHERE v.result = 'not_found')        AS not_found,
           count(v.id) FILTER (WHERE v.approval_status = 'approved') AS approved
      FROM companies c
      LEFT JOIN verifications v ON v.company_id = c.id AND v.submitted_at >= :since
     GROUP BY c.id
     ORDER BY verifications DESC, c.name
    """
)

_PROVIDERS = text(
    """
    SELECT count(*) AS invoices, COALESCE(sum(b.n), 0)::bigint AS downloads,
           COALESCE(sum(b.cents), 0)::bigint AS billed_cents
      FROM invoices i
      LEFT JOIN (SELECT invoice_id, count(*) AS n, sum(amount_cents) AS cents
                   FROM billing_events WHERE billed_at >= :since
                  GROUP BY invoice_id) b ON b.invoice_id = i.id
     WHERE i.provider_user_id IS NOT NULL AND i.created_at >= :since
    """
)


async def partner_usage(session: AsyncSession, since: datetime) -> list[dict]:
    return [dict(r) for r in (await session.execute(_PARTNERS, {"since": since})).mappings()]


async def company_usage(session: AsyncSession, since: datetime) -> list[dict]:
    return [dict(r) for r in (await session.execute(_COMPANIES, {"since": since})).mappings()]


async def direct_provider_usage(session: AsyncSession, since: datetime) -> dict:
    return dict((await session.execute(_PROVIDERS, {"since": since})).mappings().one())
