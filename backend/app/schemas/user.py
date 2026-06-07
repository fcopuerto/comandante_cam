from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    full_name: str = Field(..., max_length=200)
    password: str
    role_id: str | None = None
    preferred_language: str = "en"
    preferred_timezone: str = "UTC"


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(default=None, max_length=200)
    role_id: str | None = None
    preferred_language: str | None = None
    preferred_timezone: str | None = None
    ui_preferences: dict | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role_id: str | None
    role: str | None = None   # role name — populated at serialization time
    is_active: bool
    is_mfa_enabled: bool
    must_change_password: bool
    failed_login_count: int
    last_login: datetime | None
    last_login_ip: str | None
    preferred_language: str
    preferred_timezone: str
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    anonymised_at: datetime | None


class UserSessionResponse(BaseModel):
    id: str
    device_name: str | None
    ip_address: str | None
    last_used_at: datetime | None
    created_at: datetime
    expires_at: datetime
    is_revoked: bool


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., max_length=100)
    display_name: str | None = None
    description: str | None = None
    permissions: list[str] = []


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


class RoleResponse(BaseModel):
    id: str
    name: str
    display_name: str | None
    description: str | None
    permissions: list[str]
    is_system_role: bool
    created_at: datetime
    updated_at: datetime


class PermissionInfo(BaseModel):
    permission: str
    description: str
    category: str


class AuditLogResponse(BaseModel):
    id: int
    user_id: str | None
    user_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    detail: dict | None
    ip_address: str | None
    request_id: str | None
    severity: str
    created_at: datetime
