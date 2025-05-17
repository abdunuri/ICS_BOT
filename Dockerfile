FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

WORKDIR /app

# Nuclear option - reinstall everything
RUN rm -rf /ms-playwright && \
    playwright install chromium && \
    playwright install-deps

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "pass_bot.py"]