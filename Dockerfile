FROM python:3.9-slim-bullseye

# 1. Install JUST Chromium and its core dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    chromium \
    fonts-freefont-ttf \
    libxss1 \
    libasound2 \
    libnss3 \
    libx11-xcb1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
# 2. Configure Playwright to use system Chromium
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/bin/chromium
RUN pip install playwright && \
    pip install -r requirements.txt \
    && playwright install-deps



# 3. Force Playwright to use our system Chromium
RUN sed -i "s|'chromium',|'chromium', executable_path='/usr/bin/chromium',|g" \
    /usr/local/lib/python3.9/site-packages/playwright/__main__.py

CMD ["python", "pass_bot.py"]