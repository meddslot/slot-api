from contextlib import asynccontextmanager

from fastapi import FastAPI

from slot_api.core.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connection pool is created lazily by SQLAlchemy,
    # but we ping the DB here to fail fast on misconfiguration.
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)  # no-op, just validates connectivity
    yield
    # Shutdown: dispose the connection pool cleanly.
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
