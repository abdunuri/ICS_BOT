FROM python:3.9-slim
WORKDIR /app/ICS
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "main.py"]