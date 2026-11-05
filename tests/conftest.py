import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import slot_api.core.db as db_module
from slot_api.core.db import Base, get_session
from slot_api.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    db_module._engine = engine
    db_module._session_factory = None

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    db_module._engine = None
    db_module._session_factory = None


@pytest.fixture
async def client(db_engine):
    """
    HTTP client wired to the test engine.
    Also exposes a `seed` helper so tests can insert rows that are
    visible to the same session the route handler uses.
    """
    # Single shared session for both seeding and request handling.
    session: AsyncSession = AsyncSession(bind=db_engine, expire_on_commit=False)

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        ac.session = session  # expose for seeding in tests
        yield ac

    await session.close()
    app.dependency_overrides.clear()
