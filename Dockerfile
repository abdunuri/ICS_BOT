FROM mcr.microsoft.com/playwright/python:v1.41.1-jammy

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "pass_bot.py"]
