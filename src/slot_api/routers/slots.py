from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slot_api.core.db import get_session
from slot_api.models.slot import Slot
from slot_api.schemas.slot import SlotListResponse, SlotResponse

router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("", response_model=SlotListResponse)
async def list_slots(
    provider: Annotated[
        str | None, Query(description="Filter by provider name")
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> SlotListResponse:
    stmt = select(Slot)
    if provider is not None:
        stmt = stmt.where(Slot.provider == provider)
    stmt = stmt.order_by(Slot.start)

    result = await session.execute(stmt)
    slots = result.scalars().all()

    return SlotListResponse(slots=[SlotResponse.model_validate(s) for s in slots])
