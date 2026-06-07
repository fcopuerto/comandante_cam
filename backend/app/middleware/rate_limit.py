from slowapi import Limiter
from slowapi.util import get_remote_address


def get_real_ip(request) -> str:
    # Prefer X-Real-IP set by nginx over the direct socket address,
    # so rate limits apply per real client not per reverse-proxy IP.
    return request.headers.get("X-Real-IP") or get_remote_address(request)


limiter = Limiter(key_func=get_real_ip)


def get_user_id_or_ip(request) -> str:
    user = getattr(getattr(request, "state", None), "user", None)
    if user:
        return str(user.id)
    return get_remote_address(request)


authenticated_limiter = Limiter(key_func=get_user_id_or_ip)
