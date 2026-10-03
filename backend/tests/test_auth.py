async def test_company_admin_creates_workspace_and_employee_joins(client, auth):
    admin = await auth.register("a@acme.example.com", "company_admin", company_name="Acme")
    assert admin["user"]["company_name"] == "Acme"
    assert admin["user"]["name"] == "A User"
    code = admin["user"]["join_code"]
    assert len(code) == 8

    emp = await auth.register("e@acme.example.com", "employee", join_code=code.lower())
    assert emp["user"]["company_id"] == admin["user"]["company_id"]
    assert emp["user"]["join_code"] is None  # only admins see it


async def test_employee_needs_valid_join_code(client):
    body = {
        "name": "Rohan Mehta",
        "email": "e@x.example.com",
        "password": "password123",
        "role": "employee",
    }
    assert (await client.post("/api/v1/auth/register", json=body)).status_code == 422
    body["join_code"] = "NOPE1234"
    r = await client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 422
    assert "join code" in r.json()["detail"]


async def test_platform_admin_cannot_self_register(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "M",
            "email": "p@x.example.com",
            "password": "pw123456",
            "role": "platform_admin",
        },
    )
    assert r.status_code == 422


async def test_duplicate_email_is_conflict(client, auth):
    await auth.register("dup@x.example.com", "provider")
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Dup",
            "email": "DUP@x.example.com",
            "password": "password123",
            "role": "provider",
        },
    )
    assert r.status_code == 409


async def test_login_and_me(client, auth, headers):
    await auth.register("p@x.example.com", "provider")
    bad = await client.post(
        "/api/v1/auth/login", json={"email": "p@x.example.com", "password": "wrong-pw"}
    )
    assert bad.status_code == 401
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "who@x.example.com", "password": "password123"}
    )
    assert unknown.status_code == 401
    assert unknown.json() == bad.json()  # no hint which part was wrong

    ok = await client.post(
        "/api/v1/auth/login", json={"email": "P@x.example.com", "password": "password123"}
    )
    assert ok.status_code == 200
    me = await client.get("/api/v1/auth/me", headers=headers(ok.json()))
    assert me.json()["email"] == "p@x.example.com"
    assert me.json()["role"] == "provider"


async def test_bad_token_is_401(client):
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert (await client.get("/api/v1/auth/me")).status_code == 401
