"""
Detection microservice entry point.
Reads CAMERAS env var, spawns one DetectionWorker per camera,
starts ConfigWatcher + HealthServer, handles SIGTERM gracefully.
"""
import json
import os
import signal
import threading
import time

import structlog

logger = structlog.get_logger(__name__)


def main() -> None:
    import redis as sync_redis
    from config_watcher import ConfigWatcher
    from detector import DetectionWorker
    from health_server import HealthServer
    from redis_publisher import RedisPublisher

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    cameras_raw = os.environ.get("CAMERAS", "[]")
    alert_clips_path = os.environ.get("ALERT_CLIPS_PATH", "/data/alerts")
    min_confidence = float(os.environ.get("MIN_CONFIDENCE", "0.5"))

    cameras: list[dict] = json.loads(cameras_raw)

    # If no cameras from env, try Redis key nvr:cameras (populated by backend)
    if not cameras:
        try:
            r_init = sync_redis.Redis.from_url(redis_url, decode_responses=True)
            raw_cameras = r_init.get("nvr:cameras")
            r_init.close()
            if raw_cameras:
                cameras = json.loads(raw_cameras)
                logger.info("cameras_loaded_from_redis", count=len(cameras))
        except Exception:
            logger.warning("cameras_redis_load_failed")

    stop_event = threading.Event()
    zones: dict = {}
    zones_lock = threading.RLock()

    # Pre-load zone configs from Redis
    try:
        r = sync_redis.Redis.from_url(redis_url, decode_responses=True)
        for cam in cameras:
            raw = r.get(f"nvr:zones:{cam['id']}")
            if raw:
                zones[cam["id"]] = json.loads(raw)
        r.close()
        logger.info("initial_zones_loaded", camera_count=len(cameras))
    except Exception:
        logger.warning("initial_zones_load_failed")

    publisher = RedisPublisher(redis_url)

    detection_state: dict = {
        "cameras": len(cameras),
        "running": 0,
        "redis": "ok" if publisher.is_connected else "error",
    }

    health_server = HealthServer(detection_state=detection_state)
    health_server.start()

    config_watcher = ConfigWatcher(
        redis_url=redis_url,
        zones=zones,
        lock=zones_lock,
        stop_event=stop_event,
    )
    config_watcher.start()

    workers: list[DetectionWorker] = []
    for cam in cameras:
        w = DetectionWorker(
            camera_id=cam["id"],
            rtsp_url=cam["rtsp_url"],
            zones_ref=zones,
            zones_lock=zones_lock,
            publisher=publisher,
            stop_event=stop_event,
            alert_clips_path=alert_clips_path,
            min_confidence=min_confidence,
        )
        w.start()
        workers.append(w)

    logger.info("detection_service_started", cameras=len(cameras))

    def _shutdown(sig: int, frame: object) -> None:
        logger.info("detection_service_stopping", signal=sig)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while not stop_event.is_set():
        detection_state["running"] = sum(1 for w in workers if w.is_running)
        detection_state["redis"] = "ok" if publisher.is_connected else "error"
        stop_event.wait(timeout=5.0)

    # Graceful shutdown: join all workers (max 10 s total)
    logger.info("detection_service_joining_workers", count=len(workers))
    deadline = time.monotonic() + 10.0
    for w in workers:
        remaining = max(0.0, deadline - time.monotonic())
        w.join(timeout=remaining)
        if w.is_alive():
            logger.warning("worker_join_timeout", worker=w.name)

    health_server.stop()
    logger.info("detection_service_stopped")


if __name__ == "__main__":
    main()
