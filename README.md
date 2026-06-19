---
title: RAG Document Chat System
emoji: 🤖
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
app_port: 7860
---

# RAG Document Chat System

A Retrieval-Augmented Generation (RAG) system for chatting with uploaded documents. Built using **FastAPI** (backend) and **React / TypeScript** (frontend), and packaged into a single container.

* **Live Demo**: [Hugging Face Space](https://huggingface.co/spaces/najibfaf/rag-chatbot)
* **GitHub Repository**: [GitHub Repo](https://github.com/coditateam-cell/rag-chatbot)

---

## Features

- **Document Processing**: Parses and processes PDF, DOCX, PPTX, XLSX, XLS, and TXT files.
- **RAG chat**: Custom semantic chunk retrieval using **Qdrant** vector database and reranking with **Cohere Rerank v3**.
- **Guardrails**: Prompt injection detection, input HTML/SQL sanitization, and out-of-scope query filtering.
- **Session Isolation**: Document uploads and chat history are isolated per browser session.
- **Deployment**: Supports full local orchestration via Docker Compose and single-container execution on Hugging Face Spaces (using SQLite/local file stores).

---

## Local Setup

### Prerequisite: API Keys
Copy `.env.example` to `.env` and fill in your keys:
```env
OPENROUTER_API_KEY=sk-or-v1-...
COHERE_API_KEY=...
```

### Option A: Local Dev Stack (Docker Compose)
Runs the application alongside PostgreSQL, Qdrant, and MinIO.
```bash
docker compose up --build
```
Access the UI at [http://localhost:3000](http://localhost:3000).

### Option B: Local Lightweight Run (Without Docker)
Runs backend on port 8000 and frontend on port 5173 using SQLite and local Qdrant files.

1. **Start Backend**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # venv\Scripts\activate on Windows
   pip install -r requirements.txt
   export USE_LOCAL_MODE=true  # set USE_LOCAL_MODE=true on Windows Cmd/PowerShell
   export DISABLE_MINIO=true
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **Start Frontend**:
   ```bash
   cd ../frontend
   npm install
   npm run dev
   ```

---

## Deployed Architecture

On **Hugging Face Spaces**, the app runs as a single-port container (port 7860):
- **FastAPI** serves the compiled static React files.
- **SQLite** handles metadata and session storage.
- **Qdrant** runs locally in-memory/file mode.
- **OpenRouter** is used for embeddings and generation.

---

## Security Guardrails

- **Length limits**: Cap user queries at 4,000 characters.
- **Sanitization**: Strips HTML tags and blocks SQL injections.
- **Injection detection**: Rejects prompts containing commands to override system instructions (e.g. "ignore previous instructions", "jailbreak").
- **Topic filter**: Blocks out-of-scope questions (weather, recipes, general chit-chat) to enforce grounding to documents.

---

## Running Tests

To execute unit tests:
```bash
cd backend
pytest tests/ -v
```
