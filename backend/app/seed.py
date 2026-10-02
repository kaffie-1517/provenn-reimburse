"""Demo data: two companies, one of each role, a billing partner.

    python -m app.seed                  # accounts only
    python -m app.seed --with-activity  # plus issued invoices and claims

Safe to re-run; existing rows are left alone. Needs object storage running
for --with-activity.
"""

import argparse
import asyncio
import io
import os
import random
import uuid
from datetime import date, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from app import db, jobs, pdf, refcode, worker
from app.config import get_settings
from app.models import Company, Invoice, Partner, User, Verification
from app.security import hash_secret, new_partner_key
from app.storage import get_storage, raw_key

COMPANIES = [("Acme Corp", "pro", "ACMEJOIN"), ("Beta Inc", "starter", "BETAJOIN")]
USERS = [
    ("admin@acme.com", "company_admin", "Acme Corp"),
    ("employee@acme.com", "employee", "Acme Corp"),
    ("admin@beta.com", "company_admin", "Beta Inc"),
    ("employee@beta.com", "employee", "Beta Inc"),
    ("provider@demo.com", "provider", None),
    ("padmin@provenn.io", "platform_admin", None),
]
PARTNER = "Ledgerly Billing"
VENDORS = ["Northwind Traders", "Blue Fern Catering", "Kestrel Travel", "Monsoon Office Supply"]


def _demo_pdf(vendor: str, amount_cents: int, day: date) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(72, 760, vendor)
    c.setFont("Helvetica", 11)
    c.drawString(72, 735, f"Tax invoice · {day:%d %b %Y}")
    c.drawString(72, 690, "Description")
    c.drawRightString(520, 690, "Amount")
    c.line(72, 684, 520, 684)
    c.drawString(72, 666, "Services rendered")
    c.drawRightString(520, 666, f"INR {amount_cents / 100:,.2f}")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(520, 630, f"Total  INR {amount_cents / 100:,.2f}")
    c.showPage()
    c.save()
    return buf.getvalue()


async def seed_accounts(password: str) -> None:
    async with db.sessionmaker()() as s:
        companies = {}
        for name, plan, code in COMPANIES:
            c = await s.scalar(select(Company).where(Company.name == name))
            if c is None:
                c = Company(name=name, plan=plan, join_code=code)
                s.add(c)
                print(f"  + company  {name}  (join code {code})")
            companies[name] = c
        await s.flush()

        hashed = hash_secret(password)
        for email, role, company in USERS:
            if await s.scalar(select(User.id).where(User.email == email)):
                continue
            s.add(
                User(
                    email=email,
                    password_hash=hashed,
                    role=role,
                    company_id=companies[company].id if company else None,
                )
            )
            print(f"  + user     {email:<20} {role}")

        if not await s.scalar(select(Partner.id).where(Partner.name == PARTNER)):
            key, prefix, key_hash = new_partner_key()
            s.add(Partner(name=PARTNER, key_prefix=prefix, key_hash=key_hash))
            print(f"  + partner  {PARTNER}\n    X-Partner-Key: {key}   (shown once)")
        await s.commit()


async def seed_activity() -> None:
    storage = get_storage()
    async with db.sessionmaker()() as s:
        if await s.scalar(select(func.count()).select_from(Invoice)):
            print("  activity already present, skipping")
            return
        provider = await s.scalar(select(User).where(User.email == "provider@demo.com"))
        partner = await s.scalar(select(Partner).where(Partner.name == PARTNER))
        rng = random.Random(7)
        today = date.today()
        for i in range(8):
            vendor = VENDORS[i % len(VENDORS)]
            amount = rng.randrange(1_200, 95_000) * 100
            day = today - timedelta(days=rng.randrange(0, 25))
            inv = Invoice(
                id=uuid.uuid4(),
                reference_code=refcode.new_code(),
                provider_user_id=provider.id if i % 3 else None,
                partner_id=None if i % 3 else partner.id,
                vendor_name=vendor,
                amount_cents=amount,
                currency="INR",
                invoice_date=day,
            )
            await storage.put(raw_key(inv.id), _demo_pdf(vendor, amount, day))
            s.add(inv)
            jobs.enqueue(s, worker.STAMP_INVOICE, {"invoice_id": str(inv.id)})
        await s.commit()
    n = await worker.drain(storage)
    print(f"  + {n} invoices issued and stamped")

    # Employees submit some of them: genuine copies and one forged.
    async with db.sessionmaker()() as s:
        invoices = list(await s.scalars(select(Invoice).order_by(Invoice.created_at)))
        employees = {
            u.email: u for u in await s.scalars(select(User).where(User.role == "employee"))
        }
        plan = [
            ("employee@acme.com", 0, False),
            ("employee@acme.com", 1, False),
            ("employee@acme.com", 2, True),
            ("employee@beta.com", 3, False),
            ("employee@beta.com", 4, True),
        ]
        for email, idx, forge in plan:
            inv = invoices[idx]
            await s.refresh(inv, ["versions"])
            data = await storage.get(inv.versions[-1].storage_key)
            if forge:
                data = data.replace(b"Services rendered", b"Services rendred!", 1)
            digest = pdf.sha256(data)
            match = next((v for v in inv.versions if v.sha256_hash == digest), None)
            emp = employees[email]
            s.add(
                Verification(
                    company_id=emp.company_id,
                    submitted_by=emp.id,
                    invoice_id=inv.id,
                    extracted_code=inv.reference_code,
                    submitted_hash=digest,
                    matched_version_id=match.id if match else None,
                    file_name=f"{inv.vendor_name.lower().replace(' ', '-')}.pdf",
                    result="match" if match else "mismatch",
                )
            )
        await s.commit()
    print(f"  + {len(plan)} claims submitted")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--with-activity", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("SEED_PASSWORD", "password")
    if get_settings().env == "production" and "SEED_PASSWORD" not in os.environ:
        raise SystemExit(
            "Refusing to seed production with the default password; set SEED_PASSWORD."
        )
    try:
        print("Seeding accounts…")
        await seed_accounts(password)
        if args.with_activity:
            print("Seeding activity…")
            await seed_activity()
        shown = "(from SEED_PASSWORD)" if "SEED_PASSWORD" in os.environ else password
        print(f"Done. Demo password: {shown}")
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
