# WOL Gateway Docker Image
# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set environment variable to indicate Docker environment
ENV DOCKER_CONTAINER=true

# Install system dependencies (wakeonlan, iproute2 for host network access, and iputils-ping for ping functionality)
RUN apt-get update && \
    apt-get install -y --no-install-recommends wakeonlan iproute2 iputils-ping && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir flask pyotp qrcode pillow

# Set working directory
WORKDIR /app

# Copy application files
COPY wol_gatway.py .
COPY admin_panel.py .
COPY setup_wol.py .
COPY version.py .
COPY docker-entrypoint.sh /app/

# Make entrypoint executable
RUN chmod +x /app/docker-entrypoint.sh

# Config file will be created at runtime if it doesn't exist
# or mounted from host

# Expose the port (will be configurable via config file)
EXPOSE 5000

# Health check to ensure the service is running
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=2)" || exit 1

# Note: Running as root because we're using host networking and need to bind to privileged ports
# If you change to a port >= 1024, you can uncomment the lines below to run as non-root
# RUN useradd -m -u 1000 woluser && chown -R woluser:woluser /app
# USER woluser

# Use entrypoint script to handle setup and startup
ENTRYPOINT ["/app/docker-entrypoint.sh"]

