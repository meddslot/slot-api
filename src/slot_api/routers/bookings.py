from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slot_api.core.db import get_session
from slot_api.models.booking import Booking
from slot_api.models.slot import Slot
from slot_api.schemas.booking import BookingRequest, BookingResponse

router = APIRouter(prefix="/bookings", tags=["bookings"])

_ERROR_RESPONSES = {
    404: {"content": {"application/json": {"example": {"error": "slot not found"}}}},
    409: {"content": {"application/json": {"example": {"error": "slot not found"}}}},
}

_NOT_FOUND = JSONResponse(
    status_code=status.HTTP_404_NOT_FOUND,
    content={"error": "slot not found"},
)
_ALREADY_CANCELLED = JSONResponse(
    status_code=status.HTTP_409_CONFLICT,
    content={"error": "slot not found"},
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


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: BookingRequest,
    session: AsyncSession = Depends(get_session),
) -> BookingResponse:
    # Verify the slot exists and is still available.
    result = await session.execute(select(Slot).where(Slot.id == body.slot_id))
    slot = result.scalar_one_or_none()

    if slot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Slot '{body.slot_id}' not found",
        )
    if not slot.available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slot '{body.slot_id}' is no longer available",
        )

    # Mark slot as taken and persist the booking atomically.
    slot.available = False
    booking = Booking(slot_id=body.slot_id, name=body.name, email=body.email)
    session.add(booking)
    await session.flush()  # populate server-side defaults (id, created_at)
    await session.refresh(booking)
    await session.commit()

    return BookingResponse.model_validate(booking)
