import asyncio
import shutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
import structlog
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import from_url as redis_from_url
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.core.logging import configure_logging
from app.middleware.rate_limit import limiter
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(app_env=settings.APP_ENV, log_level=settings.LOG_LEVEL)
    logger.info("nvr_startup", version=settings.APP_VERSION, env=settings.APP_ENV)

    # 1. Validate required environment variables are present and non-empty.
    required_vars = {
        "DATABASE_URL": settings.DATABASE_URL,
        "REDIS_URL": settings.REDIS_URL,
        "FERNET_KEY": settings.FERNET_KEY,
        "RSA_PRIVATE_KEY_PATH": str(settings.RSA_PRIVATE_KEY_PATH),
        "RSA_PUBLIC_KEY_PATH": str(settings.RSA_PUBLIC_KEY_PATH),
    }
    missing = [name for name, value in required_vars.items() if not value]
    if missing:
        logger.critical("startup_missing_env_vars", missing=missing)
        raise RuntimeError(f"Required environment variables are not set: {', '.join(missing)}")

    # 2. Test database connectivity.
    try:
        db_url = settings.DATABASE_URL.replace("+asyncpg", "")
        conn = await asyncpg.connect(db_url)
        await conn.execute("SELECT 1")
        await conn.close()
        logger.info("startup_db_ok")
    except Exception as exc:
        logger.critical("startup_db_connection_failed", error=str(exc))
        raise RuntimeError("Database connection check failed at startup") from exc

    # 3. Test Redis connectivity.
    try:
        r = redis_from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        logger.info("startup_redis_ok")
    except Exception as exc:
        logger.critical("startup_redis_connection_failed", error=str(exc))
        raise RuntimeError("Redis connection check failed at startup") from exc

    # 4. Verify RSA key files exist on disk.
    for label, key_path in (
        ("RSA_PRIVATE_KEY_PATH", settings.RSA_PRIVATE_KEY_PATH),
        ("RSA_PUBLIC_KEY_PATH", settings.RSA_PUBLIC_KEY_PATH),
    ):
        if not key_path.exists():
            logger.critical("startup_rsa_key_missing", path=str(key_path), var=label)
            raise RuntimeError(f"RSA key file not found: {key_path} ({label})")
    logger.info("startup_rsa_keys_ok")

    # 5. Verify the Fernet key is structurally valid.
    try:
        _fernet = Fernet(settings.FERNET_KEY.encode())
        _fernet.decrypt(_fernet.encrypt(b"test"))
        logger.info("startup_fernet_key_ok")
    except (ValueError, InvalidToken) as exc:
        logger.critical("startup_fernet_key_invalid", error=str(exc))
        raise RuntimeError("FERNET_KEY is invalid") from exc

    # 6. Log available storage space (informational — never fails startup).
    try:
        usage = shutil.disk_usage(settings.STORAGE_PATH)
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        used_pct = (usage.used / usage.total) * 100
        logger.info(
            "startup_storage_space",
            path=str(settings.STORAGE_PATH),
            free_gb=round(free_gb, 2),
            total_gb=round(total_gb, 2),
            used_pct=round(used_pct, 1),
        )
    except Exception as exc:
        logger.warning("startup_storage_check_failed", error=str(exc))

    # 7. Seed default roles if the roles table is empty.
    try:
        from app.database import AsyncSessionFactory
        from app.services.role_service import seed_roles_if_empty
        async with AsyncSessionFactory() as db:
            await seed_roles_if_empty(db)
    except Exception as exc:
        logger.critical("startup_role_seed_failed", error=str(exc))
        raise RuntimeError("Failed to seed default roles") from exc

    # Initialise WebSocket connection counter on app state.
    app.state.ws_connection_count = 0

    # Start HLS stream manager.
    from app.services.hls_service import HLSStreamManager
    hls_manager = HLSStreamManager()
    app.state.hls_manager = hls_manager
    await hls_manager.start()

    # Start Redis → WebSocket forwarder (best-effort; skip if Redis unavailable).
    from app.routers.ws import redis_to_ws_forwarder
    redis_task = asyncio.create_task(redis_to_ws_forwarder(settings.REDIS_URL))

    yield

    redis_task.cancel()
    try:
        await redis_task
    except asyncio.CancelledError:
        pass
    await hls_manager.stop_all()
    logger.info("nvr_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NVR Pro API",
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # Attach rate limiter state
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Middleware registration order — outermost (added last) runs first on request.
    # 1. TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
    # 2. RequestIDMiddleware — must run before logging so request_id is in context
    app.add_middleware(RequestIDMiddleware)
    # 3. SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
    # 4. CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 5. AuditLogMiddleware
    from app.middleware.audit import AuditLogMiddleware
    app.add_middleware(AuditLogMiddleware)

    # Routers
    from app.routers.alerts import router as alerts_router
    from app.routers.auth import router as auth_router
    from app.routers.cameras import router as cameras_router
    from app.routers.export import router as export_router
    from app.routers.live import router as live_router
    from app.routers.notifications import router as notifications_router
    from app.routers.recordings import router as recordings_router
    from app.routers.roles import router as roles_router
    from app.routers.system import router as system_router
    from app.routers.users import router as users_router
    from app.routers.ws import router as ws_router
    from app.routers.equipment import router as equipment_router
    from app.routers.floor_plan import router as floor_plan_router
    from app.routers.terminal import router as terminal_router
    from app.routers.storage_targets import router as storage_targets_router
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(cameras_router, prefix="/api/v1")
    app.include_router(recordings_router, prefix="/api/v1")
    app.include_router(export_router, prefix="/api/v1")
    app.include_router(live_router, prefix="/api/v1")
    app.include_router(alerts_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(roles_router, prefix="/api/v1")
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(equipment_router, prefix="/api/v1")
    app.include_router(floor_plan_router, prefix="/api/v1")
    app.include_router(storage_targets_router, prefix="/api/v1")
    app.include_router(ws_router)
    app.include_router(terminal_router)

    @app.get("/health", tags=["system"])
    async def health() -> dict:
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors(), "code": "validation_error"},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("unhandled_exception", request_id=request_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    return app


app = create_app()
