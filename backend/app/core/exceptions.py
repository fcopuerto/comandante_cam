from typing import Any


class NVRException(Exception):
    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(NVRException):
    def __init__(self, resource_type: str, resource_id: Any) -> None:
        super().__init__(f"{resource_type} '{resource_id}' not found")
        self.resource_type = resource_type
        self.resource_id = resource_id


class ForbiddenError(NVRException):
    def __init__(self, required_permission: str) -> None:
        super().__init__(f"Permission required: {required_permission}")
        self.required_permission = required_permission


class ValidationError(NVRException):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"Validation error on '{field}': {message}")
        self.field = field


class ConflictError(NVRException):
    pass


class CameraConnectionError(NVRException):
    def __init__(self, ip: str, reason: str) -> None:
        super().__init__(f"Cannot connect to camera at {ip}: {reason}")
        self.ip = ip
        self.reason = reason


class StorageError(NVRException):
    pass


class AuthenticationError(NVRException):
    def __init__(self, reason: str = "Invalid credentials") -> None:
        # reason is for internal logging only — never expose to the client
        super().__init__(reason)
        self.reason = reason


class AccountLockedError(AuthenticationError):
    """Raised when too many failed attempts have temporarily locked the account."""
    pass
