FROM python:3.11-slim
RUN pip install --no-cache-dir flask
COPY server.py /app/server.py
WORKDIR /app
CMD ["python", "server.py"]
