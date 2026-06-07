import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import Settings, get_settings
from app.database import Base, get_db
from app.main import create_app


def _test_db_url() -> str:
    override = os.getenv("TEST_DATABASE_URL")
    if override:
        return override
    prod_url = get_settings().DATABASE_URL
    return prod_url.rsplit("/", 1)[0] + "/nvr_test"


TEST_DATABASE_URL = _test_db_url()
# Sync URL for schema management (psycopg2, no event-loop dependency)
TEST_DATABASE_URL_SYNC = TEST_DATABASE_URL.replace("+asyncpg", "")


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    settings = get_settings()
    object.__setattr__(settings, "DATABASE_URL", TEST_DATABASE_URL)
    # Allow httpx (Host: test) and Starlette TestClient (Host: testserver)
    object.__setattr__(settings, "ALLOWED_HOSTS", settings.ALLOWED_HOSTS + ",test,testclient,testserver")
    return settings


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi's in-memory counter before each test so they don't bleed across."""
    from app.middleware.rate_limit import limiter
    limiter._storage.reset()
    yield


@pytest.fixture(scope="session", autouse=True)
def create_schema(test_settings):
    """Drop and recreate all tables once per test session using psycopg2."""
    engine = create_engine(TEST_DATABASE_URL_SYNC, echo=False)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest_asyncio.fixture
async def db_session(create_schema) -> AsyncSession:
    """
    Per-test async engine so asyncpg connections are bound to the test's
    event loop, avoiding cross-loop InterfaceErrors.  The outer transaction
    is rolled back at teardown so no data persists between tests.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.begin()
            session = AsyncSession(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            yield session
            await session.close()
            await conn.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session) -> AsyncClient:
    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
