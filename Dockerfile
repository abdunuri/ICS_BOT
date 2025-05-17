# Use slim Python image
FROM python:3.9-slim

# Set environment variables
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install minimal dependencies (including xauth)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    xauth \
    libgtk-3-0 \
    libnss3 \
    libxss1 \
    libasound2 \
    libxtst6 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/downloads /app/filesdownloaded

# Run bot directly (no xvfb needed with headless mode)
CMD ["python", "pass_bot.py"]