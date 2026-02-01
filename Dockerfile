# Diabetes Buddy - Docker Image
# Multi-stage build for smaller final image

# Build stage
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies (git for OpenAPS docs fetching)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code (volume-mounted dirs excluded: docs, data, logs, config, scripts)
COPY agents/ ./agents/
COPY diabuddy/ ./diabuddy/
COPY web/ ./web/
COPY mcp_server.py .

# Create directories for volume mounts
RUN mkdir -p /app/docs /app/data /app/logs /app/config /app/scripts

# Create cache directory for ChromaDB
RUN mkdir -p /app/.cache/chromadb

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose web interface port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Default command: run web interface
# Use uvicorn directly for proper reload support
CMD ["python", "-m", "uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
