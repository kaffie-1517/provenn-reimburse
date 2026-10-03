from app import db
from app.models import Partner, User
from app.security import hash_secret, issue_token, new_partner_key
from tests.pdfs import tamper
from tests.test_invoices import FORM, files
from tests.test_verifications import issued_pdf, submit


async def platform_admin_headers() -> dict:
    async with db.sessionmaker()() as s:
        u = User(
            name="Platform Ops",
            email="root@example.com",
            password_hash=hash_secret("x" * 12),
            role="platform_admin",
        )
        s.add(u)
        await s.commit()
        return {"Authorization": f"Bearer {issue_token(u.id, u.role, None)}"}


async def test_usage_reports(client, auth, storage):
    key, prefix, key_hash = new_partner_key()
    async with db.sessionmaker()() as s:
        s.add(Partner(name="Billing Co", key_prefix=prefix, key_hash=key_hash))
        s.add(Partner(name="Idle Partner", key_prefix="0123456789", key_hash=key_hash))
        await s.commit()
    for _ in range(2):
        r = await client.post(
            "/api/v1/partner/invoices", data=FORM, files=files(), headers={"X-Partner-Key": key}
        )
        assert r.status_code == 202

    _, original = await issued_pdf(client, auth, storage)  # one provider invoice, downloaded
    _, emp = await auth.company("acme")
    await submit(client, emp, original)
    await submit(client, emp, tamper(original))

    h = await platform_admin_headers()
    p = (await client.get("/api/v1/admin/partners", headers=h)).json()
    assert p["window_days"] == 30
    by_name = {row["name"]: row for row in p["partners"]}
    assert by_name["Billing Co"]["invoices_issued"] == 2
    assert by_name["Idle Partner"]["invoices_issued"] == 0
    assert p["direct"] == {"invoices": 1, "downloads": 1, "billed_cents": 150000}

    c = (await client.get("/api/v1/admin/companies?days=7", headers=h)).json()
    acme = c["companies"][0]
    assert acme["name"] == "acme" and acme["members"] == 2
    assert (acme["verifications"], acme["matches"], acme["mismatches"]) == (2, 1, 1)


async def test_reports_are_platform_admin_only(client, auth):
    admin, _ = await auth.company("acme")
    assert (await client.get("/api/v1/admin/companies", headers=admin)).status_code == 403
    assert (await client.get("/api/v1/admin/companies")).status_code == 401
    h = await platform_admin_headers()
    assert (await client.get("/api/v1/admin/companies?days=0", headers=h)).status_code == 422
