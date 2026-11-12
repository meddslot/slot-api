"""Concurrency test: simultaneous POST /bookings for one email must never
exceed 5 attempts per rolling 60-second window.

Admission is insert-then-count: each request records its attempt before
counting, so admission is decided from committed state only and two
requests can never both be admitted by the same low count.

Each concurrent request targets a distinct available slot so a 409 cannot
mask a rate-limit violation — the old count-then-insert logic would have
admitted all 10 requests (10 x 201) here.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import slot_api.core.db as db_module
from slot_api.core.config import settings
from slot_api.core.db import Base
from slot_api.main import app
from slot_api.models.booking import Booking
from slot_api.models.rate_limit_attempt import RateLimitAttempt
from slot_api.models.slot import Slot

WINDOW_START = datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc)


async def test_concurrent_requests_never_exceed_rate_limit(tmp_path):
    db_path = tmp_path / "rate_limit_concurrent.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(db_url, poolclass=NullPool)

    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout = 30000")
        cur.close()

    db_module._engine = engine
    db_module._session_factory = None

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = db_module.get_session_factory()
    async with factory() as session:
        for i in range(10):
            offset = timedelta(minutes=30 * i)
            session.add(
                Slot(
                    id=f"s{i}",
                    provider="Dr Ade",
                    start=WINDOW_START + offset,
                    end=WINDOW_START + offset + timedelta(minutes=30),
                    available=True,
                )
            )
        await session.commit()

    app.dependency_overrides.clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": settings.api_key},
    ) as client:
        tasks = [
            client.post(
                "/bookings",
                json={
                    "slot_id": f"s{i}",
                    "name": "Ada Obi",
                    "email": "ada@example.com",
                },
            )
            for i in range(10)
        ]
        responses = await asyncio.gather(*tasks)

    status_codes = sorted(r.status_code for r in responses)
    assert status_codes.count(201) + status_codes.count(429) == 10, (
        f"unexpected codes: {status_codes}"
    )
    admitted = status_codes.count(201)
    assert admitted <= 5, f"rate limit exceeded under concurrency: {status_codes}"

    # Every request recorded an attempt, whatever the outcome.
    async with factory() as session:
        result = await session.execute(
            select(func.count()).select_from(RateLimitAttempt)
        )
        assert result.scalar() == 10

        # Bookings created match the admitted responses exactly.
        result = await session.execute(select(func.count()).select_from(Booking))
        assert result.scalar() == admitted

    await engine.dispose()
    db_module._engine = None
    db_module._session_factory = None
