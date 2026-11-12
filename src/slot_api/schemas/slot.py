from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator


class SlotCreate(BaseModel):
    id: str | None = None
    provider: str
    start: datetime
    end: datetime
    available: bool = True

    @field_validator("provider", mode="before")
    @classmethod
    def provider_strip(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("provider must not be empty")
        return v.strip()

    @model_validator(mode="after")
    def end_after_start(self) -> "SlotCreate":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class ResetRequest(BaseModel):
    slots: list[SlotCreate]


class SlotResponse(BaseModel):
    id: str
    provider: str
    start: datetime
    end: datetime
    available: bool

    model_config = {"from_attributes": True}


class SlotListResponse(BaseModel):
    slots: list[SlotResponse]
