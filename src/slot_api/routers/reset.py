from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from slot_api.core.db import get_session
from slot_api.models.booking import Booking
from slot_api.models.slot import Slot
from slot_api.schemas.slot import ResetRequest, SlotListResponse, SlotResponse

router = APIRouter(tags=["reset"])


@router.post("/reset", response_model=SlotListResponse)
async def reset(
    body: ResetRequest,
    session: AsyncSession = Depends(get_session),
) -> SlotListResponse:
    """Replace all slots and delete existing bookings.

    Bookings are removed first so the ``bookings.slot_id`` foreign key
    (``ON DELETE RESTRICT``) is not violated when the old slots go away.
    Slot ids are optional; omitted ids get a server-generated UUID.
    """
    await session.execute(delete(Booking))
    await session.execute(delete(Slot))

    session.add_all(
        Slot(
            id=slot.id or str(uuid4()),
            provider=slot.provider,
            start=slot.start,
            end=slot.end,
            available=slot.available,
        )
        for slot in body.slots
    )
    await session.commit()

    result = await session.execute(select(Slot).order_by(Slot.start, Slot.id))
    slots = result.scalars().all()
    return SlotListResponse(slots=[SlotResponse.model_validate(s) for s in slots])
