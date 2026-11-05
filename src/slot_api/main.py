from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from slot_api.core.db import Base, get_engine
from slot_api.models import slot  # noqa: F401 — ensures Slot is registered on Base
from slot_api.routers import slots


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    # Run DDL with advisory lock so only one gunicorn worker executes
    # create_all at a time — prevents UniqueViolationError races on startup.
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(1)"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.include_router(slots.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
