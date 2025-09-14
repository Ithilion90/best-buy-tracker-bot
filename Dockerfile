# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Keep Python output unbuffered for real-time logs
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (optional: curl for basic diagnostics)
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates curl && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src ./src

# Default: run the bot (use env vars for configuration)
CMD ["python", "-m", "src.bot"]
