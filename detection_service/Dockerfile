FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

COPY pyproject.toml uv.lock ./
RUN uv venv /opt/venv && uv sync --frozen --no-install-project

# Download YOLOv8n weights during build so they're cached in the layer.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" && \
    mkdir -p /models && \
    find /app /root -name "yolov8n.pt" 2>/dev/null | head -1 | xargs -I{} cp {} /models/yolov8n.pt

COPY . .

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "main.py"]
