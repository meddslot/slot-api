from contextlib import asynccontextmanager

from fastapi import FastAPI

from slot_api.core.db import get_engine
from slot_api.routers import bookings, slots


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_engine().dispose()


app = FastAPI(lifespan=lifespan)

app.include_router(slots.router)
app.include_router(bookings.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
