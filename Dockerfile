FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy ALL source files (includes static/ + templates/ + any other assets)
COPY main.py .
COPY templates ./templates
COPY static ./static


ENV PORT=8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "120", "main:app"]

