import os

# Must be set before app modules read settings.
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://provenn:provenn@localhost:5432/provenn_test"
    ),
)
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.storage import MemoryStorage, get_storage  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def schema():
    async with db.engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await db.dispose()


@pytest.fixture(autouse=True)
async def clean(schema):
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with db.engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def storage():
    return MemoryStorage()


@pytest.fixture
def app(storage):
    application = create_app()
    application.dependency_overrides[get_storage] = lambda: storage
    return application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class Auth:
    """Helper to create users through the public API and get auth headers."""

    def __init__(self, client: AsyncClient):
        self.client = client

    async def register(self, email: str, role: str, **extra) -> dict:
        r = await self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123", "role": role, **extra},
        )
        assert r.status_code == 201, r.text
        return r.json()

    async def company(self, name: str) -> tuple[dict, dict]:
        """Creates a company admin + one employee. Returns their auth headers."""
        admin = await self.register(f"admin@{name}.example.com", "company_admin", company_name=name)
        code = admin["user"]["join_code"]
        emp = await self.register(f"emp@{name}.example.com", "employee", join_code=code)
        return _h(admin), _h(emp)

    async def provider(self, email: str = "provider@example.com") -> dict:
        return _h(await self.register(email, "provider"))


def _h(session: dict) -> dict:
    return {"Authorization": f"Bearer {session['token']}"}


@pytest.fixture
def auth(client):
    return Auth(client)


@pytest.fixture
def headers():
    return _h
