# Base image
FROM python:3.9-slim-bullseye

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libu2f-udev \
    libvulkan1 \
    fonts-liberation \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Set work directory and copy files
WORKDIR /app
COPY . .

# Install Python packages (including Playwright)
RUN pip install --upgrade pip \
    && pip install playwright \
    && pip install -r requirements.txt \
    && playwright install chromium

# Run the bot
CMD ["python", "pass_bot.py"]
