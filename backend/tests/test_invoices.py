import asyncio

from sqlalchemy import func, select

from app import db, pdf, worker
from app.models import BillingEvent, Partner
from app.security import new_partner_key
from tests.pdfs import invoice_pdf

FORM = {
    "vendor_name": "Acme Supplies",
    "amount_cents": "150000",
    "currency": "inr",
    "invoice_date": "2026-09-01",
}


def files(data: bytes | None = None):
    return {"pdf": ("invoice.pdf", data if data is not None else invoice_pdf(), "application/pdf")}


async def issue(client, headers, **overrides):
    r = await client.post(
        "/api/v1/invoices", data={**FORM, **overrides}, files=files(), headers=headers
    )
    assert r.status_code == 202, r.text
    return r.json()


async def test_provider_issues_and_invoice_becomes_ready(client, auth, storage):
    h = await auth.provider()
    issued = await issue(client, h)
    code = issued["reference_code"]
    assert issued["status"] == "processing"

    r = await client.get(f"/api/v1/invoices/{code}")
    assert r.json()["ready"] is False and r.json()["currency"] == "INR"
    r = await client.get(f"/api/v1/invoices/{code}/download")
    assert r.status_code == 202

    await worker.drain(storage)
    r = await client.get(f"/api/v1/invoices/pnn-{code.lower()}")  # forgiving lookup
    assert r.json()["ready"] is True

    r = await client.get(f"/api/v1/invoices/{code}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert f"PNN-{code}" in r.headers["content-disposition"]
    assert pdf.find_code(r.content) == code


async def test_download_bills_exactly_once_even_concurrently(client, auth, storage):
    code = (await issue(client, await auth.provider()))["reference_code"]
    await worker.drain(storage)
    responses = await asyncio.gather(
        *(client.get(f"/api/v1/invoices/{code}/download") for _ in range(6))
    )
    assert {r.status_code for r in responses} == {200}
    async with db.sessionmaker()() as s:
        assert await s.scalar(select(func.count()).select_from(BillingEvent)) == 1


async def test_provider_list_shows_own_invoices_only(client, auth, storage):
    a, b = await auth.provider("a@example.com"), await auth.provider("b@example.com")
    await issue(client, a)
    await issue(client, a, vendor_name="Second")
    await issue(client, b)
    rows = (await client.get("/api/v1/invoices/mine", headers=a)).json()
    assert [r["vendor_name"] for r in rows] == ["Second", "Acme Supplies"]
    assert rows[0]["downloaded"] is False


async def test_validation(client, auth):
    h = await auth.provider()
    bad_type = await client.post(
        "/api/v1/invoices", data=FORM, files=files(b"\x89PNG not a pdf"), headers=h
    )
    assert bad_type.status_code == 415
    zero = await client.post(
        "/api/v1/invoices", data={**FORM, "amount_cents": "0"}, files=files(), headers=h
    )
    assert zero.status_code == 422
    assert (await client.get("/api/v1/invoices/NOPE")).status_code == 404
    assert (await client.get("/api/v1/invoices/AAAAAAAA")).status_code == 404


async def test_only_providers_can_issue(client, auth):
    _, employee = await auth.company("acme")
    r = await client.post("/api/v1/invoices", data=FORM, files=files(), headers=employee)
    assert r.status_code == 403
    r = await client.post("/api/v1/invoices", data=FORM, files=files())
    assert r.status_code == 401


async def test_partner_issues_with_api_key(client, storage):
    key, prefix, key_hash = new_partner_key()
    async with db.sessionmaker()() as s:
        s.add(Partner(name="Billing Co", key_prefix=prefix, key_hash=key_hash))
        await s.commit()

    r = await client.post(
        "/api/v1/partner/invoices", data=FORM, files=files(), headers={"X-Partner-Key": key}
    )
    assert r.status_code == 202, r.text

    wrong = key[:-2] + ("aa" if not key.endswith("aa") else "bb")
    for k in (wrong, "garbage", ""):
        r = await client.post(
            "/api/v1/partner/invoices", data=FORM, files=files(), headers={"X-Partner-Key": k}
        )
        assert r.status_code == 401


async def test_metrics_use_route_templates(client, auth):
    await client.get("/api/v1/invoices/ABCD2345")
    body = (await client.get("/metrics")).text
    assert 'route="/api/v1/invoices/{code}"' in body
    assert "ABCD2345" not in body
