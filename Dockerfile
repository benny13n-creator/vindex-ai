FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y tesseract-ocr poppler-utils \
    && (apt-get install -y tesseract-ocr-srp || true) \
    && (apt-get install -y tesseract-ocr-srp-latn || true) \
    && rm -rf /var/lib/apt/lists/*
RUN tesseract --list-langs 2>&1 || true

# Instaliraj zavisnosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiraj kod
COPY . .

# P0-A: identitet build-a. Postavlja se ovde, posle COPY, jer COPY ionako
# obara kes na svaku izmenu koda -- ARG/ENV iznad njega bi obarali i kes
# instalacije zavisnosti bez ikakve koristi.
#
# Nijedno od ovoga NIJE obavezno: Render sam postavlja RENDER_GIT_COMMIT, a
# Railway RAILWAY_GIT_COMMIT_SHA, bez ikakve konfiguracije. Ovo je za buildere
# koji to ne rade i za lokalni `docker build --build-arg GIT_SHA=$(git rev-parse HEAD)`.
ARG GIT_SHA=""
ARG BUILD_TIMESTAMP=""
ENV GIT_SHA=$GIT_SHA
ENV BUILD_TIMESTAMP=$BUILD_TIMESTAMP

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
