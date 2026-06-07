"""Subscribes to Redis nvr:config:reload:* and reloads zone config into shared dict."""
import json
import threading

import redis
import structlog

logger = structlog.get_logger(__name__)


class ConfigWatcher(threading.Thread):
    def __init__(
        self,
        redis_url: str,
        zones: dict,
        lock: threading.RLock,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True, name="config-watcher")
        self._redis_url = redis_url
        self._zones = zones
        self._lock = lock
        self._stop_event = stop_event

    def run(self) -> None:
        try:
            r = redis.Redis.from_url(self._redis_url, decode_responses=True)
            pubsub = r.pubsub()
            pubsub.psubscribe("nvr:config:reload:*")
            logger.info("config_watcher_started")

            for message in pubsub.listen():
                if self._stop_event.is_set():
                    break
                if message["type"] not in ("pmessage", "message"):
                    continue

                channel: str = message.get("channel", "")
                camera_id = channel.rsplit(":", 1)[-1]
                self._reload_zones(r, camera_id)

        except Exception:
            logger.exception("config_watcher_error")

    def _reload_zones(self, r: redis.Redis, camera_id: str) -> None:
        try:
            raw = r.get(f"nvr:zones:{camera_id}")
            if raw:
                zones_config = json.loads(raw)
                with self._lock:
                    self._zones[camera_id] = zones_config
                logger.info("zones_reloaded", camera_id=camera_id,
                            zone_count=len(zones_config))
            else:
                logger.warning("zones_reload_empty", camera_id=camera_id)
        except Exception:
            logger.exception("zones_reload_error", camera_id=camera_id)
