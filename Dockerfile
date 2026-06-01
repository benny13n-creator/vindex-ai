FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y tesseract-ocr poppler-utils \
    && (apt-get install -y tesseract-ocr-srp || true) \
    && rm -rf /var/lib/apt/lists/*
RUN tesseract --list-langs 2>&1 || true

# Instaliraj zavisnosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiraj kod
COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
