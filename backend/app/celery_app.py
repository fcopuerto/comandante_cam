from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "nvr",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.recording",
        "app.workers.export",
        "app.workers.health_check",
        "app.workers.purge",
        "app.workers.alert_consumer",
        "app.workers.notifications",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    redbeat_redis_url=settings.REDIS_URL,
)

celery_app.conf.beat_schedule = {
    "purge-old-segments": {
        "task": "nvr.purge_old_segments",
        "schedule": {"hour": 3, "minute": 0},  # daily at 03:00 UTC
    },
    "camera-health-check": {
        "task": "nvr.camera_health_check",
        "schedule": 60.0,  # every 60 seconds
    },
}


@celery_app.on_after_finalize.connect
def _start_alert_consumer(sender, **kwargs) -> None:
    """Send consume_alerts task when the worker is fully initialised."""
    from celery.signals import worker_ready

    @worker_ready.connect
    def _kick(sender, **_kwargs) -> None:
        celery_app.send_task("nvr.consume_alerts")
