# ---------------------------------------------------------------------------
# Backend API — FastAPI image (optimized for fast builds)
# ---------------------------------------------------------------------------
FROM python:3.11-slim

# Install only the truly needed system deps (no libmagic, no OCR tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt ./

# Install Python dependencies with parallel downloads + no cache
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
