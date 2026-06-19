---
title: RAG Document Chat System
emoji: 🤖
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
app_port: 7860
---

# 🤖 RAG-Based Document Chat System

A production-ready **Retrieval-Augmented Generation (RAG)** chatbot. Upload PDF, DOCX, PPTX, XLSX, XLS, and TXT documents, and chat with them intelligently. The system features a clean, responsive UI with robust security guardrails (prompt injection prevention, input sanitization, and out-of-scope filtering).

🚀 **Live Space**: [Hugging Face Space](https://huggingface.co/spaces/najibfaf/rag-chatbot)  
💻 **GitHub Repository**: [GitHub Repo](https://github.com/coditateam-cell/rag-chatbot)

---

## ✨ Features

- **📄 Multi-Format Document Processing**: Upload PDF, DOCX, PPTX, XLSX, XLS, and TXT files.
- **💬 Intelligent RAG Chat**: Retrieve relevant sections from documents using semantic search and get grounded, contextual answers from LLMs.
- **🛡️ Input Validation & Guardrails**: Built-in protection against HTML/SQL injection, prompt injection tricks, and out-of-scope conversational topics.
- **🔍 Vector Database Integration**: Utilizes Qdrant (cosine similarity) for fast and accurate semantic chunk retrieval.
- **📊 Advanced Reranking**: Integrates Cohere Rerank v3 to score and select the best contexts, falling back gracefully to vector scores if disabled.
- **⚡ Hybrid Storage Architecture**:
  - **Local Mode (Hugging Face Spaces)**: SQLite metadata database and local file-based Qdrant.
  - **Docker Compose Dev Mode**: PostgreSQL database, Qdrant service, and MinIO object storage.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│              React + TypeScript (Vite) UI              │
│       Dark glassmorphism — upload + chat interface     │
└───────────────────────────┬────────────────────────────┘
                            │ REST API / CORS
┌───────────────────────────▼────────────────────────────┐
│                 FastAPI Backend (Python)                │
│   ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌────────┐  │
│   │ Upload   │ │  Chat    │ │Guardrails │ │ Config │  │
│   │ Handler  │ │ Service  │ │  System   │ │Manager │  │
│   └──────────┘ └──────────┘ └───────────┘ └────────┘  │
│   ┌──────────────────────────────────────────────────┐ │
│   │          Orchestration Engine (RAG Pipeline)     │ │
│   │  Embed → Retrieve → Rerank → Prompt → LLM       │ │
│   └──────────────────────────────────────────────────┘ │
└────────┬──────────────────┬────────────────┬───────────┘
         │                  │                │
┌────────▼───────┐ ┌────────▼──────┐ ┌──────▼──────────┐
│  PostgreSQL/   │ │ Qdrant Vector │ │  MinIO Object/  │
│  SQLite (DB)   │ │   Database    │ │  Local Disk     │
└────────────────┘ └───────────────┘ └─────────────────┘
                            │
         ┌──────────────────┴──────────────────┐
         │           OpenRouter API            │
         │  LLM: google/gemini-2.5-flash       │
         │  Embed: nvidia/llama-nemotron-...   │
         └──────────────────────────────────────┘
```

---

## 🚀 Quick Start (Local Setup)

### Option A: Local Dev Stack (Docker Compose)
Spawns the complete architecture including PostgreSQL, Qdrant, and MinIO.

1. **Clone the repository**:
   ```bash
   git clone https://github.com/coditateam-cell/rag-chatbot.git
   cd rag-chatbot
   ```

2. **Configure environment variables**:
   Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
   *Required*:
   - `OPENROUTER_API_KEY`: OpenRouter API key for LLM + Embeddings.
   - `COHERE_API_KEY`: Cohere API key (optional, falls back to vector similarity if omitted).

3. **Start all services**:
   ```bash
   docker compose up --build
   ```

4. **Access the application**:
   Open [http://localhost:3000](http://localhost:3000) in your browser.

---

### Option B: Local Lightweight Mode (Python + Node)
Runs with embedded SQLite and local file-based Qdrant.

#### 1. Setup Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```
Copy `.env.example` to `.env` inside `backend/` and set:
```env
USE_LOCAL_MODE=true
OPENROUTER_API_KEY=your_key_here
DISABLE_MINIO=true
```
Run the server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### 2. Setup Frontend
```bash
cd ../frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🌐 Deployed on Hugging Face Spaces

The repository contains a multi-stage `Dockerfile` configured to build the React frontend static assets, copy them to the FastAPI distribution path, and run the backend.

### Deployment Environment Configuration
The following variables are configured on the live Hugging Face space settings:
- `USE_LOCAL_MODE=true` (Uses SQLite and file-system Qdrant to eliminate external database setup).
- `DISABLE_MINIO=true` (Uses local disk instead of MinIO for object uploads).
- `PYTHONPATH=/app/backend` (Proper Python package resolution).
- `OPENROUTER_API_KEY` (Configured securely as a Space Repository Secret).
- `COHERE_API_KEY` (Configured securely as a Space Repository Secret).

---

## 🛡️ Security & Validation Guardrails

To prevent prompt injection, HTML injection, SQL injection, and out-of-scope interactions:
1. **Length Limitation**: Input queries are strictly capped at 4,000 characters.
2. **HTML Sanitization**: Rejects `<script>` and sanitizes structural elements.
3. **SQL Injection Checks**: Rejects common SQL patterns (like `' OR 1=1`).
4. **Prompt Injection Guard**: Detects and filters instructions trying to override system prompts (e.g., `"ignore previous instructions"`, `"jailbreak"`, `"DAN mode"`).
5. **Out-of-Scope Detection**: Blocks unrelated general topics (such as weather, cooking recipes, or sports results) to keep interactions grounded within the context document scope.

---

## 🧪 Running Tests

To verify backend schema operations and business logic:
```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```
