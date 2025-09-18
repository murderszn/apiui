# Optimized single-stage build for Cloud Run
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements first for better caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Create necessary directories
RUN mkdir -p uploads generated_apis

# Note: Google Cloud SDK is not installed in the container
# Authentication is handled via service account key or metadata server in Cloud Run

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9999/health || exit 1

# Expose port (Backend runs on 9999)
EXPOSE 9999

# Run the application with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:9999", "--workers", "2", "--threads", "4", "--timeout", "300", "main:app"]
