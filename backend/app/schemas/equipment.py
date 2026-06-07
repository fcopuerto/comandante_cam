from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DeviceType = Literal["camera", "raspberry_pi", "display", "switch", "other"]


class EquipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    ip_address: str
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str = Field(default="pi", max_length=64)
    ssh_password: str | None = None
    ssh_key_path: str | None = None
    device_type: DeviceType = "raspberry_pi"
    location: str | None = None
    notes: str | None = None


class EquipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    ip_address: str | None = None
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_user: str | None = Field(default=None, max_length=64)
    ssh_password: str | None = None
    ssh_key_path: str | None = None
    device_type: DeviceType | None = None
    location: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class EquipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    ip_address: str
    ssh_port: int
    ssh_user: str
    has_ssh_password: bool
    ssh_key_path: str | None
    device_type: str
    location: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None
