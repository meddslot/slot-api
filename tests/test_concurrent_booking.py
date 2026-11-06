"""Concurrency test: many simultaneous POST /bookings for the same slot
must result in exactly one 201 and the rest 409.

Uses a file-based SQLite with NullPool (one connection per request) and
PRAGMA busy_timeout so writes serialise.  The partial unique index on
bookings(slot_id) WHERE status='confirmed' is the database-level guard.
"""

import asyncio
from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import slot_api.core.db as db_module
from slot_api.core.db import Base
from slot_api.main import app
from slot_api.models.slot import Slot

VALID_BODY = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}


async def test_concurrent_bookings_only_one_succeeds(tmp_path):
    db_path = tmp_path / "concurrent.db"
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
        session.add(
            Slot(
                id="s1",
                provider="Dr Ade",
                start=datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc),
                end=datetime(2026, 12, 10, 9, 30, tzinfo=timezone.utc),
                available=True,
            )
        )
        await session.commit()

    app.dependency_overrides.clear()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        tasks = [client.post("/bookings", json=VALID_BODY) for _ in range(10)]
        responses = await asyncio.gather(*tasks)

    status_codes = sorted(r.status_code for r in responses)
    assert status_codes.count(201) == 1, f"expected 1 success, got {status_codes}"
    assert status_codes.count(409) == 9, f"expected 9 conflicts, got {status_codes}"

    await engine.dispose()
    db_module._engine = None
    db_module._session_factory = None
