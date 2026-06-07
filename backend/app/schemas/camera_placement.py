from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlacementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    camera_id: str
    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)
    rotation: float = Field(default=0.0, ge=0.0, le=360.0)


class PlacementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float | None = Field(default=None, ge=0.0, le=1.0)
    y: float | None = Field(default=None, ge=0.0, le=1.0)
    rotation: float | None = Field(default=None, ge=0.0, le=360.0)


class PlacementCameraInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    location: str
    status: str
    ip_address: str


class PlacementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    floor_id: str
    camera_id: str
    x: float
    y: float
    rotation: float
    created_at: datetime
    camera: PlacementCameraInfo
