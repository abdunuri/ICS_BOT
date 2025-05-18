# Use official Python image with slim-buster base
FROM python:3.9-slim-buster

# Set environment variables
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99

# Install all required system dependencies in one layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    xvfb \
    fonts-freefont-ttf \
    libxtst6 \
    libxss1 \
    libgconf-2-4 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libatspi2.0-0 \
    libwayland-client0 \
    libwayland-server0 \
    libminizip1 \
    libharfbuzz0b \
    libopus0 \
    libwebp6 \
    libevent-2.1-6 \
    libopenjp2-7 \
    libwoff1 \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps

# Copy application code
COPY . .

# Create directories with correct permissions
RUN mkdir -p /app/downloads /app/filesdownloaded && \
    chmod -R 777 /app/downloads /app/filesdownloaded

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)"

# Run with Xvfb in background
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x16 & export DISPLAY=:99 && python pass_bot.py"]