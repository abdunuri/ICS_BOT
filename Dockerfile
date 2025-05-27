# Stage 1: Install system dependencies
FROM python:3.10-slim AS builder

# Install only essential Playwright dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
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
    libpangocairo-1.0-0 \
    libcairo2 && \
    rm -rf /var/lib/apt/lists/*

# Stage 2: Build application
FROM python:3.10-slim

# Copy dependencies from builder stage
COPY --from=builder /usr/lib /usr/lib
COPY --from=builder /usr/bin/wget /usr/bin/wget

WORKDIR /app
COPY requirements.txt .
COPY main.py .
COPY ethiopian_date.py .

# Install Python dependencies and Playwright
RUN pip install --no-cache-dir -r requirements.txt && \
    python -m playwright install chromium && \
    python -m playwright install-deps && \
    python -c "from playwright.async_api import async_playwright; print('Playwright installed successfully')"

CMD ["python3", "main.py"]