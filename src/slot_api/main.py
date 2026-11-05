from contextlib import asynccontextmanager

from fastapi import FastAPI

from slot_api.core.db import Base, get_engine
from slot_api.models import slot  # noqa: F401 — ensures Slot is registered on Base
from slot_api.routers import slots


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all tables that don't exist yet.
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: dispose the connection pool cleanly.
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.include_router(slots.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
