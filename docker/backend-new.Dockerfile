# Use Python 3.11 slim as base image
FROM python:3.11-slim

# Install system dependencies including nginx
RUN apt-get update && apt-get install -y \
    gcc \
    nginx \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set work directory
WORKDIR /app

# Create directories for uploads and generated APIs
RUN mkdir -p /app/uploads /app/generated_apis /var/cache/nginx /var/log/supervisor

# Copy requirements first for better caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Copy frontend files
COPY frontend/ /var/www/html/

# Copy nginx configuration
COPY docker/nginx.conf /etc/nginx/nginx.conf

# Create startup script
RUN echo '#!/bin/bash\ncd /app\npython main.py' > /app/start.sh && chmod +x /app/start.sh

# Create non-root user and set permissions
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app /var/www/html /app/uploads /app/generated_apis \
    && chown -R app:app /var/log/nginx /var/cache/nginx /etc/nginx \
    && chown app:app /app/start.sh

# Switch to non-root user
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application
CMD ["/app/start.sh"]
