# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (lightweight; wheels cover most packages, but keep gcc for safety)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose default port (Render sets $PORT; we still expose 8000 for local)
EXPOSE 8000

# Healthcheck hits FastAPI health endpoint without extra deps
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import os,urllib.request,sys; port=os.environ.get('PORT','8000');
print(urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2).read()); sys.exit(0)" || exit 1

# Default to 8000 locally; Render will inject $PORT at runtime
ENV PORT=8000

# Start uvicorn
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
