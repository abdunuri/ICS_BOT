FROM python:3.9-slim

# Set Playwright browsers path
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright
RUN pip install playwright

# Install browsers
RUN playwright install chromium

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/downloads /app/filesdownloaded

CMD ["python", "pass_bot.py"]