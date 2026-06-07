from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FloorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    level: int = 0


class FloorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    level: int | None = None


class FloorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    building_id: str
    name: str
    level: int
    has_image: bool = False
    created_at: datetime
    updated_at: datetime | None
