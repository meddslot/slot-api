from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from slot_api.core.db import get_engine
from slot_api.routers import bookings, slots


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_engine().dispose()


app = FastAPI(lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "slot not found"},
    )


app.include_router(slots.router)
app.include_router(bookings.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
