from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BuildingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str | None = None
    address: str | None = None


class BuildingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    description: str | None = None
    address: str | None = None


class BuildingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str | None
    address: str | None
    created_at: datetime
    updated_at: datetime | None
    floor_count: int = 0
