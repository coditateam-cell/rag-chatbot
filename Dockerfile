# ==========================================
# Stage 1: Build the React Frontend
# ==========================================
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Build the FastAPI Backend
# ==========================================
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies (curl for healthchecks, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Pre-download NLTK data as root to prevent permission errors at runtime (UID 1000 cannot write to site-packages)
RUN python -c "import nltk; nltk.download('punkt', download_dir='/usr/local/lib/python3.11/site-packages/llama_index/core/_static/nltk_cache'); nltk.download('punkt_tab', download_dir='/usr/local/lib/python3.11/site-packages/llama_index/core/_static/nltk_cache'); nltk.download('stopwords', download_dir='/usr/local/lib/python3.11/site-packages/llama_index/core/_static/nltk_cache')"

# Copy backend code
COPY backend/ ./backend/

# Copy compiled frontend from Stage 1 into the backend directory so FastAPI can serve it
COPY --from=frontend-builder /app/frontend/dist ./backend/frontend_dist

# Set environment variables for Local Mode (SQLite, Local Qdrant, Local Disk Storage)
ENV USE_LOCAL_MODE=true
ENV OPENROUTER_API_KEY=""
ENV DISABLE_MINIO=true
ENV FRONTEND_DIST=/app/backend/frontend_dist
ENV CONFIG_DIR=/app/backend/config
ENV PYTHONPATH=/app/backend

# Hugging Face Spaces maps port 7860
EXPOSE 7860

# Ensure data directory exists and has correct permissions
RUN mkdir -p /app/data

# Create a non-root user (UID 1000 is required by Hugging Face Spaces)
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user

# Run the FastAPI application using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
