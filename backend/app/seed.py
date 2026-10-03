"""Demo data: two employers, their finance teams and employees, airline / hotel /
ride vendors, two API billing partners, and a realistic month of claims.

    python -m app.seed                  # accounts only
    python -m app.seed --with-activity  # plus issued invoices and claims

Safe to re-run; existing rows are left alone. Needs object storage (or
STORAGE_DIR) for --with-activity. Employers and people are fictional; vendor
names are only used as text on generated sample invoices.
"""

import argparse
import asyncio
import io
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from app import db, jobs, pdf, refcode, worker
from app.config import get_settings
from app.models import BillingEvent, Company, Invoice, Partner, User, Verification
from app.security import hash_secret, new_partner_key
from app.storage import get_storage, raw_key

# ── accounts ─────────────────────────────────────────────────────────────────

COMPANIES = [
    ("Northstar Technologies", "pro", "NORTHSTAR"),
    ("Kavya Retail", "starter", "KAVYARETAIL"),
]

# (name, email, role, company)
USERS = [
    ("Priya Sharma", "priya.sharma@northstar.demo", "company_admin", "Northstar Technologies"),
    ("Rohan Mehta", "rohan.mehta@northstar.demo", "employee", "Northstar Technologies"),
    ("Aisha Khan", "aisha.khan@northstar.demo", "employee", "Northstar Technologies"),
    ("Vikram Rao", "vikram.rao@kavyaretail.demo", "company_admin", "Kavya Retail"),
    ("Ananya Iyer", "ananya.iyer@kavyaretail.demo", "employee", "Kavya Retail"),
    ("Air India", "billing@airindia.demo", "provider", None),
    ("IndiGo", "billing@goindigo.demo", "provider", None),
    ("Taj Hotels", "billing@tajhotels.demo", "provider", None),
    ("Platform Ops", "ops@provenn.demo", "platform_admin", None),
]

# Ride apps integrate through their billing systems, not the portal.
PARTNERS = ["Uber India", "Rapido"]


# ── sample invoices ──────────────────────────────────────────────────────────


@dataclass
class Doc:
    vendor: str
    title: str
    number: str
    meta: list[tuple[str, str]]
    items: list[tuple[str, int]]  # (description, amount in paise)
    gst_rate: float
    customer: str
    company: str
    days_ago: int
    file_name: str
    lines: list[str] = field(default_factory=list)

    @property
    def subtotal(self) -> int:
        return sum(a for _, a in self.items)

    @property
    def gst(self) -> int:
        return round(self.subtotal * self.gst_rate)

    @property
    def total(self) -> int:
        return self.subtotal + self.gst


def _inr(paise: int) -> str:
    return f"INR {paise / 100:,.2f}"


def render(doc: Doc, day: date) -> bytes:
    """A plain, believable invoice layout. Text only, no marks or logos."""
    ink = Color(0.16, 0.14, 0.12)
    muted = Color(0.45, 0.41, 0.36)
    rule = Color(0.82, 0.78, 0.72)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, _ = A4
    left, right = 56, w - 56

    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(left, 780, doc.vendor)
    c.setFont("Helvetica", 10)
    c.setFillColor(muted)
    c.drawString(left, 763, doc.title)
    c.drawRightString(right, 780, f"No. {doc.number}")
    c.drawRightString(right, 765, day.strftime("%d %b %Y"))

    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, 726, "BILLED TO")
    c.setFont("Helvetica", 10)
    c.drawString(left, 712, doc.customer)
    c.setFillColor(muted)
    c.drawString(left, 698, doc.company)

    y = 726
    for k, v in doc.meta:
        c.setFillColor(muted)
        c.setFont("Helvetica", 9)
        c.drawString(330, y, k)
        c.setFillColor(ink)
        c.setFont("Helvetica", 10)
        c.drawRightString(right, y, v)
        y -= 15

    y = min(y, 680) - 20
    c.setStrokeColor(rule)
    c.line(left, y, right, y)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(muted)
    c.drawString(left, y - 16, "DESCRIPTION")
    c.drawRightString(right, y - 16, "AMOUNT")
    y -= 26
    c.line(left, y, right, y)

    c.setFont("Helvetica", 10)
    c.setFillColor(ink)
    for desc, amount in doc.items:
        y -= 20
        c.drawString(left, y, desc)
        c.drawRightString(right, y, _inr(amount))

    y -= 14
    c.line(330, y, right, y)
    for label, amount in [
        ("Subtotal", doc.subtotal),
        (f"GST ({doc.gst_rate * 100:g}%)", doc.gst),
    ]:
        y -= 18
        c.setFillColor(muted)
        c.drawString(330, y, label)
        c.setFillColor(ink)
        c.drawRightString(right, y, _inr(amount))
    y -= 24
    c.setFont("Helvetica-Bold", 12)
    c.drawString(330, y, "Total")
    c.drawRightString(right, y, _inr(doc.total))

    c.setFont("Helvetica", 8)
    c.setFillColor(muted)
    yy = 120
    for line in doc.lines + ["This is a computer generated invoice and does not need a signature."]:
        c.drawString(left, yy, line)
        yy -= 12
    c.showPage()
    c.save()
    return buf.getvalue()


NS, KR = "Northstar Technologies", "Kavya Retail"

# key -> document. Keys are referenced by CLAIMS below.
DOCS: dict[str, Doc] = {
    "ai_del_bom": Doc(
        "Air India",
        "E-Ticket cum Tax Invoice",
        "AI2610-448213",
        [("PNR", "9PFQLF"), ("Flight", "AI 805  DEL to BOM"), ("Class", "Economy")],
        [
            ("Base fare", 5_480_00),
            ("Airport & user development fee", 612_00),
            ("Fuel surcharge", 350_00),
        ],
        0.05,
        "Rohan Mehta",
        NS,
        21,
        "AirIndia_eTicket_9PFQLF.pdf",
        ["Fare rules apply. Baggage: 15 kg check-in, 7 kg cabin."],
    ),
    "taj_mumbai": Doc(
        "Taj Hotels",
        "Tax Invoice · Guest Folio",
        "TLE/26/10871",
        [("Property", "Taj Lands End, Mumbai"), ("Stay", "2 nights"), ("Room", "Deluxe, sea view")],
        [("Room charges (2 × 14,500.00)", 29_000_00), ("In-room dining", 2_340_00)],
        0.18,
        "Rohan Mehta",
        NS,
        20,
        "Taj_Folio_TLE-10871.pdf",
    ),
    "uber_bom": Doc(
        "Uber India",
        "Trip Receipt · Tax Invoice",
        "UBR-7Q2K9X41",
        [
            ("Trip", "BOM T2 to Bandra Kurla Complex"),
            ("Ride", "Uber Premier"),
            ("Distance", "14.2 km"),
        ],
        [("Trip fare", 548_00), ("Airport surcharge", 80_00), ("Booking fee", 25_00)],
        0.05,
        "Rohan Mehta",
        NS,
        21,
        "Uber_Receipt_BOM.pdf",
    ),
    "indigo_blr_hyd": Doc(
        "IndiGo",
        "Tax Invoice",
        "6E-IN-55190842",
        [("PNR", "K7WZ2M"), ("Flight", "6E 6382  BLR to HYD"), ("Class", "Economy")],
        [("Base fare", 3_920_00), ("Convenience fee", 399_00), ("Airport charges", 486_00)],
        0.05,
        "Aisha Khan",
        NS,
        12,
        "IndiGo_Invoice_K7WZ2M.pdf",
    ),
    "rapido_hyd": Doc(
        "Rapido",
        "Ride Receipt",
        "RPD-HYD-904417",
        [("Trip", "HITEC City to Gachibowli"), ("Ride", "Auto"), ("Distance", "6.8 km")],
        [("Ride fare", 162_00), ("Platform fee", 15_00)],
        0.05,
        "Aisha Khan",
        NS,
        11,
        "Rapido_Receipt_904417.pdf",
    ),
    "ai_bom_del": Doc(
        "Air India",
        "E-Ticket cum Tax Invoice",
        "AI2610-451977",
        [("PNR", "3HTRVA"), ("Flight", "AI 678  BOM to DEL"), ("Class", "Economy")],
        [
            ("Base fare", 6_150_00),
            ("Airport & user development fee", 640_00),
            ("Fuel surcharge", 350_00),
        ],
        0.05,
        "Ananya Iyer",
        KR,
        9,
        "AirIndia_eTicket_3HTRVA.pdf",
    ),
    "taj_blr": Doc(
        "Taj Hotels",
        "Tax Invoice · Guest Folio",
        "TWE/26/22104",
        [("Property", "Taj West End, Bengaluru"), ("Stay", "1 night"), ("Room", "Superior")],
        [("Room charges (1 × 16,800.00)", 16_800_00), ("Laundry", 620_00)],
        0.18,
        "Ananya Iyer",
        KR,
        6,
        "Taj_Folio_TWE-22104.pdf",
    ),
    "uber_blr": Doc(
        "Uber India",
        "Trip Receipt · Tax Invoice",
        "UBR-3M8D1P27",
        [("Trip", "Kempegowda Airport to MG Road"), ("Ride", "UberGo"), ("Distance", "36.5 km")],
        [("Trip fare", 812_00), ("Airport toll", 120_00), ("Booking fee", 25_00)],
        0.05,
        "Ananya Iyer",
        KR,
        6,
        "Uber_Receipt_BLR.pdf",
    ),
    "indigo_del_blr": Doc(
        "IndiGo",
        "Tax Invoice",
        "6E-IN-55233019",
        [("PNR", "P4XNQD"), ("Flight", "6E 2137  DEL to BLR"), ("Class", "Economy")],
        [("Base fare", 5_210_00), ("Convenience fee", 399_00), ("Airport charges", 512_00)],
        0.05,
        "Rohan Mehta",
        NS,
        2,
        "IndiGo_Invoice_P4XNQD.pdf",
    ),
}

# (employee email, doc key or None for a non-ProveNN receipt, forged?, decision)
CLAIMS = [
    ("rohan.mehta@northstar.demo", "ai_del_bom", False, "approved"),
    ("rohan.mehta@northstar.demo", "taj_mumbai", True, "rejected"),
    ("rohan.mehta@northstar.demo", "uber_bom", False, "pending"),
    ("aisha.khan@northstar.demo", "indigo_blr_hyd", False, "pending"),
    ("aisha.khan@northstar.demo", "rapido_hyd", False, "approved"),
    ("aisha.khan@northstar.demo", None, False, "pending"),
    ("ananya.iyer@kavyaretail.demo", "ai_bom_del", False, "pending"),
    ("ananya.iyer@kavyaretail.demo", "taj_blr", True, "pending"),
    ("ananya.iyer@kavyaretail.demo", "uber_blr", False, "approved"),
]

UNISSUED = Doc(
    "Chai Point",
    "Cash Memo",
    "CP-HYD-0091",
    [("Outlet", "Hyderabad Airport")],
    [("Team snacks", 1_180_00)],
    0.05,
    "Aisha Khan",
    NS,
    10,
    "ChaiPoint_receipt.pdf",
)


def forge(data: bytes, doc: Doc) -> bytes:
    """Bumps the total's first digit, the way an edited claim would look."""
    old = f"{doc.total / 100:,.2f}"
    new = str((int(old[0]) + 2) % 10 or 9) + old[1:]
    assert old.encode() in data, "total not found in content stream"
    return data.replace(old.encode(), new.encode())


# ── seeding ──────────────────────────────────────────────────────────────────


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
        for name, email, role, company in USERS:
            if await s.scalar(select(User.id).where(User.email == email)):
                continue
            s.add(
                User(
                    name=name,
                    email=email,
                    password_hash=hashed,
                    role=role,
                    company_id=companies[company].id if company else None,
                )
            )
            print(f"  + user     {email:<30} {role}")

        for partner in PARTNERS:
            if await s.scalar(select(Partner.id).where(Partner.name == partner)):
                continue
            key, prefix, key_hash = new_partner_key()
            s.add(Partner(name=partner, key_prefix=prefix, key_hash=key_hash))
            print(f"  + partner  {partner:<12} X-Partner-Key: {key}   (shown once)")
        await s.commit()


async def seed_activity() -> None:
    storage = get_storage()
    today = date.today()
    now = datetime.now(UTC)

    async with db.sessionmaker()() as s:
        if await s.scalar(select(func.count()).select_from(Invoice)):
            print("  activity already present, skipping")
            return
        providers = {
            u.name: u for u in await s.scalars(select(User).where(User.role == "provider"))
        }
        partners = {p.name: p for p in await s.scalars(select(Partner))}

        issued: dict[str, Invoice] = {}
        for key, doc in DOCS.items():
            day = today - timedelta(days=doc.days_ago)
            inv = Invoice(
                id=uuid.uuid4(),
                reference_code=refcode.new_code(),
                provider_user_id=providers[doc.vendor].id if doc.vendor in providers else None,
                partner_id=partners[doc.vendor].id if doc.vendor in partners else None,
                vendor_name=doc.vendor,
                amount_cents=doc.total,
                currency="INR",
                invoice_date=day,
                purchase_ref=doc.number,
                created_at=now - timedelta(days=doc.days_ago, hours=2),
            )
            await storage.put(raw_key(inv.id), render(doc, day))
            s.add(inv)
            jobs.enqueue(s, worker.STAMP_INVOICE, {"invoice_id": str(inv.id)})
            issued[key] = inv
        await s.commit()
    n = await worker.drain(storage)
    print(f"  + {n} invoices issued and stamped")

    async with db.sessionmaker()() as s:
        people = {u.email: u for u in await s.scalars(select(User))}
        finance = {u.company_id: u for u in people.values() if u.role == "company_admin"}

        for i, (email, key, forged, decision) in enumerate(CLAIMS):
            emp = people[email]
            if key is None:
                doc, inv, data = UNISSUED, None, render(UNISSUED, today)
            else:
                doc, inv = DOCS[key], await s.get(Invoice, issued[key].id)
                await s.refresh(inv, ["versions"])
                data = await storage.get(inv.versions[-1].storage_key)
                # The employee downloaded it first; that's what bills the issuer.
                s.add(
                    BillingEvent(
                        invoice_id=inv.id,
                        idempotency_key=f"download:{inv.id}",
                        amount_cents=inv.amount_cents,
                        billed_at=now - timedelta(days=doc.days_ago, hours=1),
                    )
                )
                if forged:
                    data = forge(data, doc)

            digest = pdf.sha256(data)
            match = (
                next((v for v in inv.versions if v.sha256_hash == digest), None) if inv else None
            )
            submitted = now - timedelta(days=max(doc.days_ago - 1, 0), hours=3 + i)
            s.add(
                Verification(
                    company_id=emp.company_id,
                    submitted_by=emp.id,
                    invoice_id=inv.id if inv else None,
                    extracted_code=inv.reference_code if inv else None,
                    submitted_hash=digest,
                    matched_version_id=match.id if match else None,
                    file_name=doc.file_name,
                    result="match" if match else ("mismatch" if inv else "not_found"),
                    approval_status=decision,
                    approved_by=finance[emp.company_id].id if decision != "pending" else None,
                    approved_at=submitted + timedelta(hours=20) if decision != "pending" else None,
                    submitted_at=submitted,
                )
            )
        await s.commit()
    print(f"  + {len(CLAIMS)} claims submitted (2 forged, 1 not issued)")


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
