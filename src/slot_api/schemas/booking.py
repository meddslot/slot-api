from datetime import datetime

from pydantic import BaseModel, EmailStr


class BookingRequest(BaseModel):
    slot_id: str
    name: str
    email: EmailStr


class BookingResponse(BaseModel):
    id: str
    slot_id: str
    name: str
    email: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
