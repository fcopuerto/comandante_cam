from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from app.schemas.user import UserResponse


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str
    mfa_code: str | None = None
    remember_device: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: dict | None = None  # serialized UserResponse


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Refresh token may be sent in body (non-browser clients) or HttpOnly cookie
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str
    new_password: str = Field(min_length=12)


class CheckPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str


class CheckPasswordResponse(BaseModel):
    pwned: bool
    message: str


class MFASetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_data_url: str


class MFAVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=8)


class MFADisableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=8)


class BackupCodesResponse(BaseModel):
    codes: list[str]
    warning: str = "Store these codes securely. Each can only be used once."


class SessionResponse(BaseModel):
    id: str
    device_name: str | None
    ip_address: str | None
    last_used_at: datetime | None
    created_at: datetime
    expires_at: datetime
    is_current: bool = False


class UserMeResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role_name: str | None
    permissions: list[str]
    is_mfa_enabled: bool
    must_change_password: bool
    preferred_timezone: str
    preferred_language: str
    created_at: datetime


class TokenPayload(BaseModel):
    sub: str
    email: str
    role: str
    permissions: list[str]
    jti: str
