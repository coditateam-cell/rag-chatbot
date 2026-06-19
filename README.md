---
title: RAG Document Chat System
emoji: 🤖
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
app_port: 7860
---

# 🤖 RAG Document Chat System

A production-grade **Retrieval-Augmented Generation (RAG)** chatbot that lets you upload documents and chat with them intelligently. Built with FastAPI, LlamaIndex, OpenRouter, Qdrant, and PostgreSQL.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Hugging%20Face%20Spaces-yellow)](https://huggingface.co/spaces/YOUR_USERNAME/rag-document-chat)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue)](https://github.com/YOUR_USERNAME/rag-document-chat)

---

## ✨ Features

| Feature | Details |
|---------|---------|
| 📄 **Document Upload** | PDF, DOCX, PPTX, XLSX, XLS, TXT (up to 10 MB) |
| 💬 **RAG Chat** | Semantic retrieval + LLM-grounded answers |
| 🛡️ **Guardrails** | Prompt injection detection + out-of-scope blocking |
| 🔍 **Vector Search** | Qdrant cosine similarity (top-20 retrieval) |
| 📊 **Reranking** | Cohere Rerank v3 with fallback to vector scores |
| 🗂️ **Chat History** | Per-session history stored in PostgreSQL |
| ⚡ **LlamaIndex** | SentenceSplitter chunking (400 tokens, 12% overlap) |
| 🔒 **Input Validation** | HTML/SQL injection sanitization + length limits |
| 📈 **Rate Limiting** | 100 requests/60s per IP |

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│              React + TypeScript (Vite) UI              │
│         Dark glassmorphism — upload + chat + docs      │
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
│  PostgreSQL    │ │ Qdrant Vector │ │  MinIO Object   │
│ (Metadata DB)  │ │   Database    │ │  Storage (local)│
└────────────────┘ └───────────────┘ └─────────────────┘
                            │
         ┌──────────────────┴──────────────────┐
         │           OpenRouter API            │
         │  LLM: openai/gpt-4o                 │
         │  Embed: openai/text-embedding-3-small│
         └──────────────────────────────────────┘
```

---

## 🚀 Quick Start (Local with Docker Compose)

### Prerequisites
- Docker + Docker Compose
- OpenRouter API key ([get one free](https://openrouter.ai))
- Cohere API key ([get one free](https://cohere.com)) — optional, falls back to vector scores

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/rag-document-chat.git
cd rag-document-chat

# 2. Set up environment variables
cp .env.example .env
# Edit .env and add your API keys:
#   OPENROUTER_API_KEY=sk-or-v1-...
#   COHERE_API_KEY=...

# 3. Start all services
docker compose up --build

# 4. Open the app
open http://localhost:3000
```

### Services started by Docker Compose

| Service | Port | Purpose |
|---------|------|---------|
| Backend (FastAPI) | `8000` | REST API |
| Frontend (Vite dev) | `3000` | React UI |
| PostgreSQL | `5432` | Metadata store |
| Qdrant | `6333` | Vector database |
| MinIO | `9000` | File storage |

---

## 🌐 Hugging Face Spaces Deployment

The repo includes a `Dockerfile.hf` for HF Spaces that runs the entire application (frontend + backend + SQLite + local vector store) in a single Python container.

### Deploy to HF Spaces

```bash
# 1. Create a new Space on huggingface.co/new-space
#    SDK: Docker, Port: 7860

# 2. Add secret in Space settings:
#    OPENROUTER_API_KEY (and optionally COHERE_API_KEY)

# 3. Create a README.md or upload files in the HF Space repo, and copy all code.
#    IMPORTANT: Rename `Dockerfile.hf` to `Dockerfile` when uploading to Hugging Face Spaces.
```

---

## ⚙️ Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | ✅ | OpenRouter API key for LLM + embeddings |
| `COHERE_API_KEY` | Optional | Cohere reranker (falls back to vector scores) |
| `POSTGRES_USER` | ✅ | PostgreSQL username |
| `POSTGRES_PASSWORD` | ✅ | PostgreSQL password |
| `POSTGRES_DB` | ✅ | PostgreSQL database name |
| `POSTGRES_HOST` | ✅ | PostgreSQL host (default: `postgres`) |
| `QDRANT_HOST` | ✅ | Qdrant host (default: `qdrant`) |
| `QDRANT_URL` | Optional | Qdrant Cloud URL (overrides HOST/PORT) |
| `QDRANT_API_KEY` | Optional | Qdrant Cloud API key |
| `MINIO_ROOT_USER` | Local only | MinIO access key |
| `MINIO_ROOT_PASSWORD` | Local only | MinIO secret key |
| `DISABLE_MINIO` | HF Spaces | Set `true` to skip MinIO |
| `FRONTEND_ORIGIN` | ✅ | Allowed CORS origin |

---

## 🛡️ Security & Guardrails

### Input Validation
- **Length limit**: queries capped at 4,000 characters
- **HTML sanitization**: `<script>` tags stripped
- **SQL injection**: patterns like `' OR 1=1` blocked

### Prompt Injection Detection
Blocks patterns like:
- `ignore previous instructions`
- `you are now a different AI`
- `reveal your system prompt`
- `jailbreak`, `DAN mode`

### Out-of-Scope Detection
Rejects unrelated queries (weather, sports scores, recipes, jokes).

---

## 📖 RAG Pipeline

```
User Query
    │
    ▼
InputValidator (sanitize + length check)
    │
    ▼
GuardrailSystem (injection + scope check)
    │
    ▼
EmbeddingGenerator (OpenRouter text-embedding-3-small)
    │
    ▼
Qdrant Search (top-20 cosine similarity, threshold ≥ 0.7)
    │
    ▼
Cohere Reranker (top-5 selected, fallback to vector scores)
    │
    ▼
Prompt Construction (8,000 char limit, truncate context)
    │
    ▼
LLM (OpenRouter gpt-4o) → Grounded Answer
    │
    ▼
PostgreSQL (persist interaction + metadata)
    │
    ▼
React UI (render answer + source citations)
```

---

## 🧪 Running Tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

---

## 📁 Project Structure

```
rag-document-chat/
├── backend/
│   ├── app/
│   │   ├── handlers/           # Core business logic
│   │   │   ├── chat_service.py         # RAG chat orchestration
│   │   │   ├── document_processor.py   # Parsing + chunking + embedding
│   │   │   ├── embedding_generator.py  # OpenRouter embeddings
│   │   │   ├── guardrail_system.py     # Security guardrails
│   │   │   ├── input_validator.py      # Input sanitization
│   │   │   ├── llm_service.py          # OpenRouter LLM
│   │   │   ├── orchestration_engine.py # Retrieve + rerank + prompt
│   │   │   ├── reranker_service.py     # Cohere / Jina reranking
│   │   │   └── upload_handler.py       # File upload + validation
│   │   ├── routers/            # API endpoints
│   │   ├── db/                 # PostgreSQL schema + connection
│   │   ├── config/             # YAML configuration
│   │   └── main.py             # FastAPI app entry point
│   ├── Dockerfile              # Backend-only Docker image
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/         # React components
│   │   ├── api/                # API client
│   │   └── App.tsx
│   └── package.json
├── Dockerfile.hf               # HF Spaces all-in-one container
├── docker-compose.yml          # Local development stack
└── README.md
```

---

## 🤝 Built For

Submission for **RAG-based Document Chat System** (Round 2 Assignment)

**Tech Stack**: FastAPI · LlamaIndex · OpenRouter · Qdrant · PostgreSQL · React · TypeScript · Docker
