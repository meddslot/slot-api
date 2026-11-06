import base64
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from slot_api.core.db import get_session
from slot_api.models.booking import Booking
from slot_api.models.idempotency_key import IdempotencyKey
from slot_api.models.rate_limit_attempt import RateLimitAttempt
from slot_api.models.slot import Slot
from slot_api.schemas.booking import (
    BookingListResponse,
    BookingRequest,
    BookingResponse,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])

_ERROR_RESPONSES = {
    404: {"content": {"application/json": {"example": {"error": "slot not found"}}}},
    409: {"content": {"application/json": {"example": {"error": "slot not found"}}}},
}

_ERR_CONTENT = {
    "content": {"application/json": {"example": {"error": "slot not found"}}}
}

_NOT_FOUND = JSONResponse(
    status_code=status.HTTP_404_NOT_FOUND,
    content={"error": "slot not found"},
)
_ALREADY_CANCELLED = JSONResponse(
    status_code=status.HTTP_409_CONFLICT,
    content={"error": "slot not found"},
)
_BAD_LIMIT = JSONResponse(
    status_code=status.HTTP_400_BAD_REQUEST,
    content={"error": "slot not found"},
)

_ERR_BODY = {"error": "slot not found"}


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------


def _request_hash(body: BookingRequest) -> str:
    """SHA-256 of the normalised JSON body (after trim/lowercase validators)."""
    return hashlib.sha256(body.model_dump_json().encode()).hexdigest()


async def _store_idempotency(
    session: AsyncSession,
    key: str | None,
    req_hash: str,
    status_code: int,
    body: dict,
    booking_id: str | None,
) -> None:
    """Persist an idempotency record and commit.  No-op when key is absent."""
    if key is None:
        return
    session.add(
        IdempotencyKey(
            key=key,
            request_hash=req_hash,
            status_code=status_code,
            response_body=json.dumps(body),
            booking_id=booking_id,
        )
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------
# Cursor encodes (created_at ISO, id) so we can page by (created_at, id) and
# handle ties when two bookings share the same timestamp.


def _encode_cursor(created_at: datetime, booking_id: str) -> str:
    payload = f"{created_at.isoformat()}|{booking_id}"
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    payload = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, booking_id = payload.split("|", 1)
    return datetime.fromisoformat(ts), booking_id


# ---------------------------------------------------------------------------
# Routes — list must be declared before /{id} so FastAPI resolves correctly
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=BookingListResponse,
    responses={
        400: {"content": {"application/json": {"example": {"error": "slot not found"}}}}
    },
)
async def list_bookings(
    email: Annotated[
        str | None, Query(description="Filter by email (case-insensitive)")
    ] = None,
    cursor: Annotated[str | None, Query(description="Pagination cursor")] = None,
    limit: Annotated[
        int | None, Query(description="Page size (1-50, default 10)")
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> BookingListResponse | JSONResponse:
    page_size = limit if limit is not None else 10
    if not (1 <= page_size <= 50):
        return _BAD_LIMIT

    stmt = select(Booking)

    if email is not None:
        stmt = stmt.where(func.lower(Booking.email) == email.lower())

    if cursor is not None:
        cursor_dt, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Booking.created_at > cursor_dt,
                and_(Booking.created_at == cursor_dt, Booking.id > cursor_id),
            )
        )

    stmt = stmt.order_by(Booking.created_at.asc(), Booking.id.asc())
    stmt = stmt.limit(page_size + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_next = len(rows) > page_size
    page = rows[:page_size]

    next_cursor = _encode_cursor(page[-1].created_at, page[-1].id) if has_next else None

    return BookingListResponse(
        bookings=[BookingResponse.model_validate(b) for b in page],
        next_cursor=next_cursor,
    )


@router.get("/{id}", response_model=BookingResponse, responses=_ERROR_RESPONSES)
async def get_booking(
    id: str,
    session: AsyncSession = Depends(get_session),
) -> BookingResponse | JSONResponse:
    result = await session.execute(select(Booking).where(Booking.id == id))
    booking = result.scalar_one_or_none()

    if booking is None:
        return _NOT_FOUND

    return BookingResponse.model_validate(booking)


@router.delete("/{id}", response_model=BookingResponse, responses=_ERROR_RESPONSES)
async def cancel_booking(
    id: str,
    session: AsyncSession = Depends(get_session),
) -> BookingResponse | JSONResponse:
    result = await session.execute(select(Booking).where(Booking.id == id))
    booking = result.scalar_one_or_none()

    if booking is None:
        return _NOT_FOUND

    if booking.status == "cancelled":
        return _ALREADY_CANCELLED

    slot_result = await session.execute(select(Slot).where(Slot.id == booking.slot_id))
    slot = slot_result.scalar_one_or_none()
    if slot is not None:
        slot.available = True

    booking.status = "cancelled"
    await session.commit()
    await session.refresh(booking)

    return BookingResponse.model_validate(booking)


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: _ERR_CONTENT,
        404: _ERR_CONTENT,
        409: _ERR_CONTENT,
        422: _ERR_CONTENT,
        429: _ERR_CONTENT,
    },
)
async def create_booking(
    body: BookingRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> BookingResponse | JSONResponse:
    idem_key = request.headers.get("idempotency-key")
    req_hash = _request_hash(body)

    # --- Idempotency replay -------------------------------------------------
    if idem_key is not None:
        result = await session.execute(
            select(IdempotencyKey).where(IdempotencyKey.key == idem_key)
        )
        record = result.scalar_one_or_none()
        if record is not None:
            if record.request_hash == req_hash:
                return JSONResponse(
                    status_code=record.status_code,
                    content=json.loads(record.response_body),
                )
            return JSONResponse(
                status_code=422,
                content=_ERR_BODY,
            )

    # --- Rate limit: max 5 attempts per email per minute --------------------
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    count_result = await session.execute(
        select(func.count())
        .select_from(RateLimitAttempt)
        .where(
            RateLimitAttempt.email == body.email,
            RateLimitAttempt.created_at >= cutoff,
        )
    )
    attempt_count = count_result.scalar() or 0

    if attempt_count >= 5:
        oldest_result = await session.execute(
            select(func.min(RateLimitAttempt.created_at)).where(
                RateLimitAttempt.email == body.email,
                RateLimitAttempt.created_at >= cutoff,
            )
        )
        oldest = oldest_result.scalar()
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        retry_after = max(
            1,
            math.ceil(
                (
                    oldest + timedelta(seconds=60) - datetime.now(timezone.utc)
                ).total_seconds()
            ),
        )
        return JSONResponse(
            status_code=429,
            content=_ERR_BODY,
            headers={"Retry-After": str(retry_after)},
        )

    # Record this attempt so it counts even if the booking fails.
    session.add(RateLimitAttempt(email=body.email))
    await session.commit()

    # --- Lock the slot row to serialise concurrent attempts -----------------
    result = await session.execute(
        select(Slot).where(Slot.id == body.slot_id).with_for_update()
    )
    slot = result.scalar_one_or_none()

    if slot is None:
        await _store_idempotency(session, idem_key, req_hash, 404, _ERR_BODY, None)
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=_ERR_BODY)

    now = datetime.now(timezone.utc)
    start = slot.start
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if start <= now:
        await _store_idempotency(session, idem_key, req_hash, 400, _ERR_BODY, None)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=_ERR_BODY)

    if not slot.available:
        await _store_idempotency(session, idem_key, req_hash, 409, _ERR_BODY, None)
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=_ERR_BODY)

    # --- Create the booking -------------------------------------------------
    slot.available = False
    booking = Booking(slot_id=body.slot_id, name=body.name, email=body.email)
    session.add(booking)

    try:
        await session.flush()
        await session.refresh(booking)
    except (IntegrityError, OperationalError):
        # The partial unique index (IntegrityError) or a stale-snapshot
        # conflict (OperationalError) caught a race that slipped past
        # FOR UPDATE.
        await session.rollback()
        await _store_idempotency(session, idem_key, req_hash, 409, _ERR_BODY, None)
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=_ERR_BODY)

    booking_data = BookingResponse.model_validate(booking).model_dump(mode="json")

    # Add the idempotency record to the same transaction so both commit
    # atomically (or both roll back).
    if idem_key is not None:
        session.add(
            IdempotencyKey(
                key=idem_key,
                request_hash=req_hash,
                status_code=201,
                response_body=json.dumps(booking_data),
                booking_id=booking.id,
            )
        )

    try:
        await session.commit()
    except (IntegrityError, OperationalError):
        await session.rollback()
        await _store_idempotency(session, idem_key, req_hash, 409, _ERR_BODY, None)
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=_ERR_BODY)

    return BookingResponse.model_validate(booking)
