"""
Publish alert payloads to Redis nvr:alerts channel.
Buffers up to MAX_BUFFER events in memory when Redis is unavailable.
"""
from __future__ import annotations

import json
import threading
from collections import deque
from typing import Optional

import redis
import structlog

logger = structlog.get_logger(__name__)

_CHANNEL = "nvr:alerts"
_MAX_BUFFER = 100


class RedisPublisher:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._r: Optional[redis.Redis] = None
        self._buffer: deque[dict] = deque(maxlen=_MAX_BUFFER)
        self._lock = threading.Lock()
        self._connect()

    def publish(self, payload: dict) -> None:
        with self._lock:
            if self._r is None:
                self._buffer.append(payload)
                if not self._connect():
                    return

            try:
                # Drain buffer before new event (FIFO order preserved)
                while self._buffer:
                    old = self._buffer.popleft()
                    self._r.publish(_CHANNEL, json.dumps(old))  # type: ignore[union-attr]
                self._r.publish(_CHANNEL, json.dumps(payload))  # type: ignore[union-attr]
                logger.debug("alert_published", camera_id=payload.get("camera_id"))
            except Exception:
                logger.warning("redis_publish_failed", camera_id=payload.get("camera_id"))
                self._buffer.append(payload)
                self._r = None
                self._connect()

    @property
    def is_connected(self) -> bool:
        if self._r is None:
            return False
        try:
            self._r.ping()
            return True
        except Exception:
            self._r = None
            return False

    def _connect(self) -> bool:
        try:
            r = redis.Redis.from_url(self._redis_url, decode_responses=True)
            r.ping()
            self._r = r
            logger.info("redis_publisher_connected")
            return True
        except Exception:
            logger.warning("redis_publisher_connect_failed")
            self._r = None
            return False
