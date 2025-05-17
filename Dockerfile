# Use slim Python image instead of full Playwright image
FROM python:3.9-slim

# Set environment variables
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV DISPLAY=:99

# Install minimal dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    libgtk-3-0 \
    libnotify-dev \
    libgconf-2-4 \
    libnss3 \
    libxss1 \
    libasound2 \
    libxtst6 \
    xvfb && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/downloads /app/filesdownloaded

# Start X virtual framebuffer and run bot
CMD xvfb-run python pass_bot.py