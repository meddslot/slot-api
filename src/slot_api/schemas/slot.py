from datetime import datetime

from pydantic import BaseModel


class SlotResponse(BaseModel):
    id: str
    provider: str
    start: datetime
    end: datetime
    available: bool

    model_config = {"from_attributes": True}


class SlotListResponse(BaseModel):
    slots: list[SlotResponse]
