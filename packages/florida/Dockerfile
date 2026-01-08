# Build from repo root: docker build -f packages/florida/Dockerfile -t florida-api .
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY packages/florida/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy core package (dependency)
COPY packages/core/src/core ./src/core/

# Copy Florida application code
COPY packages/florida/src/ ./src/

# Set Python path
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/api/fl/health || exit 1

# Run the application
CMD ["uvicorn", "florida.api.app:app", "--host", "0.0.0.0", "--port", "8001"]
