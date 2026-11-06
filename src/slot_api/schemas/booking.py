from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class BookingRequest(BaseModel):
    slot_id: str
    name: str
    email: EmailStr

    @field_validator("slot_id", mode="before")
    @classmethod
    def slot_id_not_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("slot_id must not be empty")
        return v

    @field_validator("name", mode="before")
    @classmethod
    def name_strip(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("email", mode="before")
    @classmethod
    def email_strip_and_lower(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("email must not be empty")
        return v.strip().lower()


class BookingResponse(BaseModel):
    id: str
    slot_id: str
    name: str
    email: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingListResponse(BaseModel):
    bookings: list[BookingResponse]
    next_cursor: str | None
