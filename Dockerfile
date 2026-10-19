# One image for all three Python services; docker-compose picks which script runs.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

# print logs immediately instead of buffering them
ENV PYTHONUNBUFFERED=1
