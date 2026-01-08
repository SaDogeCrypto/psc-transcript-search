# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from main pyproject.toml
COPY pyproject.toml ./
RUN pip install --no-cache-dir build && \
    pip install --no-cache-dir .

# Install Florida package
COPY packages/florida/pyproject.toml ./packages/florida/
COPY packages/florida/src/ ./packages/florida/src/
RUN pip install --no-cache-dir ./packages/florida/

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY packages/florida/src/florida/ ./florida/
COPY packages/florida/alembic/ ./alembic/
COPY packages/florida/alembic.ini ./

# Create data directory
RUN mkdir -p /data/audio /data/florida

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/fl/health || exit 1

# Run Florida API
EXPOSE 8000
CMD ["uvicorn", "florida.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
