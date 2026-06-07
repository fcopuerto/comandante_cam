FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ultralytics 8.3+ properly handles torch weights_only changes (works with torch 2.6+).
# CPU-only torch wheel avoids the 2.5 GB CUDA default download.
RUN pip install --no-cache-dir \
    "torch==2.5.1+cpu" \
    "torchvision==0.20.1+cpu" \
    --extra-index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    "numpy<2.0" \
    "ultralytics==8.3.50" \
    "opencv-python-headless==4.9.0.80" \
    "redis==5.0.4" \
    "shapely==2.0.4" \
    "supervision==0.20.0" \
    "structlog==24.1.0" \
    "pytest==8.2.0"

# Download YOLOv8n weights during build so they're cached in the layer.
# ultralytics 8.3+ saves to CWD (/app/yolov8n.pt), not ~/.config/Ultralytics/.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" && \
    mkdir -p /models && \
    find /app /root -name "yolov8n.pt" 2>/dev/null | head -1 | xargs -I{} cp {} /models/yolov8n.pt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "main.py"]
