"""Minimal HTTP health server on port 8001 for Docker healthcheck."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import structlog

logger = structlog.get_logger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            state = self.server.detection_state  # type: ignore[attr-defined]
            body = json.dumps({
                "status": "ok",
                "cameras": state.get("cameras", 0),
                "running": state.get("running", 0),
                "redis": state.get("redis", "unknown"),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass  # suppress default HTTP access logging


class HealthServer(threading.Thread):
    def __init__(self, detection_state: dict, port: int = 8001) -> None:
        super().__init__(daemon=True, name="health-server")
        self._port = port
        self._state = detection_state
        self._server: HTTPServer | None = None

    def run(self) -> None:
        server = HTTPServer(("", self._port), _HealthHandler)
        server.detection_state = self._state  # type: ignore[attr-defined]
        self._server = server
        logger.info("health_server_started", port=self._port)
        server.serve_forever()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
