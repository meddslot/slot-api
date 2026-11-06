import base64
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from slot_api.core.db import get_session
from slot_api.models.booking import Booking
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
        # Return rows where (created_at, id) comes strictly after the cursor,
        # ordered oldest-first.
        stmt = stmt.where(
            or_(
                Booking.created_at > cursor_dt,
                and_(Booking.created_at == cursor_dt, Booking.id > cursor_id),
            )
        )

    stmt = stmt.order_by(Booking.created_at.asc(), Booking.id.asc())
    stmt = stmt.limit(page_size + 1)  # fetch one extra to detect next page

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

    # Free the slot back up and mark the booking cancelled.
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
    },
)
async def create_booking(
    body: BookingRequest,
    session: AsyncSession = Depends(get_session),
) -> BookingResponse | JSONResponse:
    result = await session.execute(select(Slot).where(Slot.id == body.slot_id))
    slot = result.scalar_one_or_none()

    if slot is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "slot not found"},
        )

    now = datetime.now(tz=slot.start.tzinfo)
    if slot.start <= now:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "slot not found"},
        )

    if not slot.available:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "slot not found"},
        )

    # Mark slot as taken and persist the booking atomically.
    # name and email are already trimmed/lowercased by BookingRequest validators.
    slot.available = False
    booking = Booking(slot_id=body.slot_id, name=body.name, email=body.email)
    session.add(booking)
    await session.flush()  # populate server-side defaults (id, created_at)
    await session.refresh(booking)
    await session.commit()

    return BookingResponse.model_validate(booking)
