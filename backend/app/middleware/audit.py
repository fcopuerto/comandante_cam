"""
AuditLogMiddleware — fires a background audit entry for every mutating request.
Runs after the response is sent so it never adds latency.
"""
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Routes that should not be auto-logged (they write their own specific entries)
_SKIP_PATHS = frozenset({
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/logout-all",
    "/api/v1/auth/refresh",
})


def _action_from_request(method: str, path: str) -> str:
    """Derive a coarse action label from HTTP method + path."""
    parts = [p for p in path.strip("/").split("/") if p]
    resource = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "unknown")
    action_map = {
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }
    verb = action_map.get(method, method.lower())
    return f"{resource}_{verb}"


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if request.method not in _MUTATING_METHODS:
            return response
        if request.url.path in _SKIP_PATHS:
            return response
        if response.status_code >= 500:
            return response

        # Best-effort audit — never block or raise
        try:
            user = getattr(request.state, "user", None)
            request_id = getattr(request.state, "request_id", None)
            action = _action_from_request(request.method, request.url.path)
            logger.info(
                "audit_request",
                action=action,
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                user_id=user.id if user else None,
                request_id=request_id,
            )
        except Exception:
            pass

        return response
