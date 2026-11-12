from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from slot_api.core.auth import verify_api_key
from slot_api.core.db import get_engine
from slot_api.routers import bookings, reset, slots


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_engine().dispose()


app = FastAPI(lifespan=lifespan, dependencies=[Depends(verify_api_key)])


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "slot not found"},
    )


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
app.include_router(reset.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
