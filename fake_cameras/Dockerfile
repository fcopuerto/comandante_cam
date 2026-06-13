FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_SYSTEM_PYTHON=1

RUN uv pip install --system flask

COPY server.py /app/server.py
WORKDIR /app
CMD ["python", "server.py"]
