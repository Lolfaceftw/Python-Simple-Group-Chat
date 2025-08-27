# Multi-stage Docker build for the Chat Application

# Build stage
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt requirements-optional.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt -r requirements-optional.txt

# Copy source code
COPY . .

# Install the application
RUN pip install --no-cache-dir .

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Create non-root user
RUN groupadd -r chatapp && useradd -r -g chatapp chatapp

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/chat-server /usr/local/bin/chat-client /usr/local/bin/

# Copy application code
COPY --from=builder /app/chat_app ./chat_app
COPY --from=builder /app/config.example.json ./config.example.json
COPY --from=builder /app/config.example.yaml ./config.example.yaml

# Create directories for logs and configuration
RUN mkdir -p /app/logs /app/config && \
    chown -R chatapp:chatapp /app

# Switch to non-root user
USER chatapp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 8080)); s.close()" || exit 1

# Expose ports
EXPOSE 8080 8081

# Default command (can be overridden)
CMD ["chat-server"]