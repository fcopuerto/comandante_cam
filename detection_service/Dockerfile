FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

COPY pyproject.toml ./
# uv export can't handle PyTorch's +cpu local version identifiers cross-platform.
# Install directly: torch/torchvision from the CPU wheel index, rest from PyPI.
RUN uv pip install --system --no-cache \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1 torchvision==0.20.1 && \
    uv pip install --system --no-cache \
    "numpy<2.0" ultralytics==8.3.50 opencv-python-headless==4.9.0.80 \
    redis==5.0.4 shapely==2.0.4 supervision==0.20.0 structlog==24.1.0

# Download YOLOv8n weights during build so they're cached in the layer.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" && \
    mkdir -p /models && \
    find /app /root -name "yolov8n.pt" 2>/dev/null | head -1 | xargs -I{} cp {} /models/yolov8n.pt

COPY . .

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "main.py"]
