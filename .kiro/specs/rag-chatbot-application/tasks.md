# Implementation Plan: RAG Chatbot Application

## Overview

This plan breaks the RAG Chatbot Application into incremental coding tasks covering the full stack: Docker infrastructure, FastAPI backend services (Upload Handler, Document Processor, Embedding Generator, Orchestration Engine, Reranker Service, Chat Service, Input Validator, Guardrail System, Configuration Manager), PostgreSQL/Qdrant/MinIO data layer, and the React/TypeScript frontend. Property-based tests (Hypothesis) are included as optional sub-tasks alongside every core component.

## Tasks

- [x] 1. Project structure, Docker Compose, and shared types
  - [x] 1.1 Scaffold repository layout and Docker Compose services
    - Create `docker-compose.yml` defining services: `qdrant`, `minio`, `postgres`, `backend`
    - Add `rag_network` bridge network; configure `depends_on` with healthchecks for all data services
    - Add volume mappings for Qdrant data, MinIO data, and PostgreSQL data
    - Add `healthcheck` blocks (interval 10 s, timeout 5 s) for each data service
    - Create `backend/Dockerfile` for the FastAPI image
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11_

  - [x] 1.2 Define shared Python types and database schema
    - Create `backend/app/models/` with Pydantic models: `DocumentMetadata`, `ChatSession`, `ChatMessage`, `AppConfig`, `UploadResult`, `ProcessingResult`, `ChatResponse`, `RankedChunk`, `Chunk`
    - Write `backend/app/db/schema.sql` with `documents` and `chat_sessions`/`chat_messages` DDL as specified in the design
    - Create `backend/app/db/connection.py` with async SQLAlchemy engine setup
    - _Requirements: 2.9, 7.2, 7.5, 11.1, 11.2, 11.6_

- [x] 2. Configuration Manager
  - [x] 2.1 Implement `ConfigurationManager` class
    - Load JSON/YAML config files from a directory specified at startup
    - Validate all parameters against defined ranges (chunk_size_tokens 300–500, overlap_percentage 10–15, reranker_top_k 1–20)
    - Provide default values for optional fields; raise descriptive errors naming the failing parameter
    - Implement `load()`, `reload()` (within 5 s), and `get(key)` methods
    - On reload failure retain the previous valid configuration
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13_

  - [x] 2.2 Write property test for configuration validation (P18)
    - **Property 18: Configuration validation rejects out-of-range parameters**
    - **Validates: Requirements 5.8, 5.9, 5.10**

  - [x] 2.3 Write property test for configuration round-trip (P19)
    - **Property 19: Configuration round-trip preserves all values**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.13**

  - [x] 2.4 Write property test for failed reload retention (P20)
    - **Property 20: Failed configuration reload retains the previous valid configuration**
    - **Validates: Requirements 5.11**

  - [x] 2.5 Write unit test for optional field defaults
    - Omit optional field → verify default applied
    - _Requirements: 5.12_

- [x] 3. Upload Handler
  - [x] 3.1 Implement `UploadHandler` class
    - Validate file extension against allowed set {pdf, docx, pptx, xlsx, xls, txt, png, jpg, jpeg}
    - Validate MIME type and reject mismatches
    - Enforce 10 MB size limit (reject with `file_too_large` error)
    - Reject empty/zero-byte files with `invalid_file` error
    - Scan for malicious content (executables, scripts, embedded payloads); reject with `security_threat`
    - Store accepted files in MinIO; generate and return a unique UUID `document_id`
    - On MinIO failure return `storage_failure` error
    - Write initial `documents` record to PostgreSQL with `processing_status = pending`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 4.4, 4.5, 4.6_

  - [x]* 3.2 Write property test for supported formats always accepted (P1)
    - **Property 1: Supported file formats are always accepted**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**

  - [x]* 3.3 Write property test for unsupported formats always rejected (P2)
    - **Property 2: Unsupported file formats are always rejected**
    - **Validates: Requirements 1.7, 1.11**

  - [x]* 3.4 Write property test for oversized files always rejected (P3)
    - **Property 3: Files exceeding the size limit are always rejected**
    - **Validates: Requirements 1.9, 4.4**

  - [x]* 3.5 Write property test for unique document identifiers (P4)
    - **Property 4: Successful uploads always return a unique document identifier**
    - **Validates: Requirements 1.8**

  - [x]* 3.6 Write property test for empty files always rejected (P5)
    - **Property 5: Empty files are always rejected**
    - **Validates: Requirements 1.10**

  - [x]* 3.7 Write property test for metadata fields completeness (P8)
    - **Property 8: Document metadata records always contain all required fields**
    - **Validates: Requirements 2.9**

  - [x] 3.8 Write unit test for MinIO storage failure path
    - Mock MinIO to throw → verify `storage_failure` HTTP 503 returned
    - _Requirements: 1.12_

- [x] 4. Document Processor and Embedding Generator
  - [x] 4.1 Implement `EmbeddingGenerator` with retry logic
    - Wrap OpenRouter embedding API call with 30 s timeout per chunk
    - Implement exponential backoff retry (1 s, 2 s, 4 s) up to 3 attempts
    - Raise `EmbeddingFailureError` after all retries exhausted
    - _Requirements: 2.5, 2.6, 3.3, 3.4_

  - [x] 4.2 Implement `DocumentProcessor` class
    - Dispatch to LlamaIndex parsers for PDF and DOCX; Unstructured.io for PPTX, XLSX, XLS; OCR for PNG/JPG/JPEG
    - Extract UTF-8 text preserving paragraph, heading, table, and list structure
    - Apply LlamaIndex recursive chunking (300–500 tokens, 10–15% overlap) with contextual summaries from adjacent chunks
    - Call `EmbeddingGenerator` per chunk; write vectors + payload to Qdrant
    - Payload must include: `chunk_id`, `document_id`, `chunk_text`, `position_in_document`, `contextual_summary`
    - Update `processing_status` in PostgreSQL to `completed` or `failed` with error detail
    - Handle parse timeout (> 60 s), corrupted file, OCR failure, embedding failure with descriptive error logging
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.7, 2.8, 2.9, 2.10, 2.11, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

  - [x]* 4.3 Write property test for chunk token count and overlap bounds (P6)
    - **Property 6: Chunk token count and overlap are always within configured bounds**
    - **Validates: Requirements 2.4, 5.10**

  - [x]* 4.4 Write property test for embedding payload required fields (P7)
    - **Property 7: Embedding payloads always contain all required metadata fields**
    - **Validates: Requirements 2.7**

  - [x]* 4.5 Write unit test for embedding retry behaviour
    - Mock 3 consecutive OpenRouter timeouts → verify exactly 3 retries then failure
    - _Requirements: 2.6_

  - [x]* 4.6 Write unit test for document structure preservation
    - Supply known-structure PDF/DOCX → verify headings, tables, lists preserved
    - _Requirements: 2.10, 9.1, 9.2_

- [x] 5. Input Validator and Guardrail System
  - [x] 5.1 Implement `InputValidator` class
    - Reject empty strings, whitespace-only strings, and queries exceeding 2000 characters
    - Escape or remove HTML tags (e.g., `<script>`, `<img>`)
    - Remove SQL injection patterns (e.g., `' OR 1=1`, `; DROP TABLE`)
    - Sanitise special characters in file names and all text input fields
    - _Requirements: 3.1, 3.2, 4.7_

  - [x]* 5.2 Write property test for invalid queries always rejected (P9)
    - **Property 9: Invalid queries are always rejected by the Input Validator**
    - **Validates: Requirements 3.1**

  - [x]* 5.3 Write property test for sanitised output contains no HTML/SQL (P10)
    - **Property 10: Sanitised queries never contain HTML tags or SQL injection patterns**
    - **Validates: Requirements 3.2, 4.7**

  - [x] 5.4 Implement `GuardrailSystem` class
    - Detect prompt injection patterns: instruction overrides, role manipulation, system-prompt extraction
    - Detect out-of-scope queries; reject with appropriate error
    - Enforce hard 4000-character ceiling; reject with `query_too_long` error
    - _Requirements: 4.1, 4.2, 4.3, 4.8, 4.9_

  - [x]* 5.5 Write property test for prompt injection always rejected (P11)
    - **Property 11: Prompt injection patterns are always detected and rejected**
    - **Validates: Requirements 4.1, 4.2**

  - [x]* 5.6 Write property test for queries exceeding guardrail limit always rejected (P12)
    - **Property 12: Queries exceeding the guardrail length limit are always rejected**
    - **Validates: Requirements 4.8, 4.9**

  - [x]* 5.7 Write unit test for out-of-scope query rejection
    - Supply known out-of-scope queries → verify rejection with `out_of_scope` error
    - _Requirements: 4.3_

- [x] 6. Reranker Service
  - [x] 6.1 Implement `RerankerService` with Cohere and Jina providers
    - Define provider-agnostic `rerank(query, chunks) -> List[RankedChunk]` interface
    - Implement Cohere Rerank v3 adapter; implement Jina Reranker v2 adapter
    - Select active provider from `ConfigurationManager` at startup; support switching without code changes
    - Enforce 50 ms per-batch timeout; log performance warning if exceeded
    - Return chunks sorted in descending order by reranking score; scores must be in [0.0, 1.0]
    - Accept configurable `top_k` (1–20) from configuration
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.8, 13.9_

  - [x]* 6.2 Write property test for reranked chunks sorted descending (P26)
    - **Property 26: Reranked chunks are always sorted by descending reranking score**
    - **Validates: Requirements 13.5**

  - [x]* 6.3 Write property test for reranking scores in [0.0, 1.0] (P28)
    - **Property 28: Reranking scores are always in [0.0, 1.0]**
    - **Validates: Requirements 13.8**

  - [x] 6.4 Write unit test for provider selection
    - Configure Cohere and Jina in turn → verify correct provider is invoked
    - _Requirements: 13.3, 13.6_

- [x] 7. Orchestration Engine
  - [x] 7.1 Implement `OrchestrationEngine` using LlamaIndex query pipeline
    - Retrieve top-20 chunks from Qdrant by cosine similarity; similarity scores must be in [0.0, 1.0]
    - Return retrieved chunks sorted in descending order by cosine similarity score
    - Evaluate at most 100 chunks regardless of total Vector Store size
    - Timeout retrieval at 30 s; return retrieval timeout error
    - Pass retrieved chunks to `RerankerService`; on reranker failure fall back to original similarity order
    - Select top-`top_k` (from config, default 5) highest-scored chunks after reranking
    - Search across all document embeddings in Vector Store
    - Return no-results response when all similarity scores < 0.7 threshold
    - _Requirements: 3.5, 3.6, 3.7, 10.1, 10.2, 10.3, 10.4, 10.8, 10.9, 10.10, 10.11, 13.7_

  - [x] 7.2 Implement prompt construction with truncation
    - Concatenate system instructions + context chunks (separated by newlines) + user query
    - Apply prompt template substituting `{system_instructions}`, `{context_chunks}`, `{user_query}`
    - If total prompt > 8000 characters, truncate `context_chunks` only; preserve both instructions and query
    - _Requirements: 3.8, 10.5, 10.6, 10.7_

  - [x]* 7.3 Write property test for top-k selection returns highest-ranked chunks (P13)
    - **Property 13: Top-k chunk selection always returns the highest-ranked chunks**
    - **Validates: Requirements 3.7, 10.3, 10.4**

  - [x]* 7.4 Write property test for constructed prompts contain all three components (P14)
    - **Property 14: Constructed prompts always contain all three required components**
    - **Validates: Requirements 3.8, 10.5, 10.6**

  - [x]* 7.5 Write property test for prompt truncation preserves instructions and query (P15)
    - **Property 15: Prompts exceeding 8000 characters are truncated while preserving instructions and query**
    - **Validates: Requirements 10.7**

  - [x]* 7.6 Write property test for similarity scores in [0.0, 1.0] (P21)
    - **Property 21: Retrieved vector similarity scores are always in [0.0, 1.0]**
    - **Validates: Requirements 10.1**

  - [x]* 7.7 Write property test for retrieved chunks ordered descending by similarity (P22)
    - **Property 22: Retrieved chunks are always ordered by descending similarity score**
    - **Validates: Requirements 10.2**

  - [x] 7.8 Write property test for max 100 chunks evaluated (P23)
    - **Property 23: Maximum chunk evaluation is bounded at 100**
    - **Validates: Requirements 10.11**

  - [x] 7.9 Write property test for reranker fallback produces ordered results (P27)
    - **Property 27: Reranker fallback always produces ordered results**
    - **Validates: Requirements 13.7**

- [x] 8. Chat Service and Session Management
  - [x] 8.1 Implement `ChatService` class
    - Create a new UUID `session_id` on session start; ensure uniqueness
    - Run query through `InputValidator` → `GuardrailSystem` → `EmbeddingGenerator` → `OrchestrationEngine` → `LLM_Service`
    - On embedding failure return `api_unavailable` error; on LLM failure return `response_failure` error
    - On no-results (all scores < 0.7) return configured no-results message without calling LLM
    - Persist completed interactions to PostgreSQL: `query_text`, `response`, `timestamp`, `session_id`, `retrieved_chunk_ids`, `reranking_scores`, `reranking_provider`, `reranking_duration_ms`
    - Implement `get_history(session_id)` returning session messages; archive expired sessions
    - _Requirements: 3.4, 3.10, 3.11, 3.12, 3.13, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 13.10_

  - [x] 8.2 Write property test for no-results threshold enforced (P16)
    - **Property 16: No-results threshold is always enforced**
    - **Validates: Requirements 3.13, 10.10**

  - [x] 8.3 Write property test for completed interactions persist all required fields (P17)
    - **Property 17: Completed chat interactions always persist all required fields**
    - **Validates: Requirements 3.12, 11.2**

  - [x] 8.4 Write property test for sessions always have unique identifiers (P24)
    - **Property 24: Sessions always have unique identifiers**
    - **Validates: Requirements 11.1**

  - [x] 8.5 Write property test for all chat messages have non-null timestamps (P25)
    - **Property 25: All chat messages have non-null timestamps**
    - **Validates: Requirements 11.6**

  - [x] 8.6 Write property test for reranking metadata always persisted (P29)
    - **Property 29: Reranking metadata is always persisted after a completed query**
    - **Validates: Requirements 13.10**

  - [x] 8.7 Write unit test for embedding failure propagation
    - Mock embedding failure → verify `api_unavailable` error returned to caller
    - _Requirements: 3.4_

  - [x] 8.8 Write unit test for session history context maintenance
    - Create session, submit multiple queries, request history → verify context maintained
    - _Requirements: 11.4_

- [x] 9. FastAPI Backend API and Middleware
  - [x] 9.1 Wire all services into FastAPI app with middleware
    - Register routers: `POST /documents/upload`, `GET /documents`, `DELETE /documents/{document_id}`, `POST /chat/query`, `GET /chat/history`
    - Implement rate limiting middleware: 100 requests per client per 60-second window; return HTTP 429 on breach
    - Configure CORS to allow only the frontend origin from environment variable
    - Add structured error handler returning `{"error": ..., "detail": ...}` for 400, 401, 403, 429, 500; include unique `error_id` on 500
    - Implement request logging middleware (timestamp + request details)
    - Wire `ConfigurationManager` at startup; expose hot-reload endpoint
    - _Requirements: 4.10, 4.11, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 9.2 Write unit test for rate limiting
    - Send 101 requests in window → verify 101st returns HTTP 429
    - _Requirements: 4.10, 4.11_

  - [x] 9.3 Write unit test for CORS header enforcement
    - Verify `Access-Control-Allow-Origin` matches env-var origin only
    - _Requirements: 7.12_

  - [x] 9.4 Write integration test for document upload → list → delete lifecycle
    - Upload a document, verify 201 + document_id; list → verify entry; delete → verify removed
    - _Requirements: 7.1, 7.2, 7.3, 7.7_

- [x] 10. Checkpoint — Backend complete
  - Ensure all backend unit tests, property tests, and integration tests pass; resolve any failures before proceeding. Ask the user if questions arise.

- [x] 11. React/TypeScript Frontend
  - [x] 11.1 Scaffold React TypeScript app and shared API client
    - Initialise Vite + React + TypeScript project under `frontend/`
    - Create typed API client (`frontend/src/api/`) covering all five backend endpoints with proper request/response types
    - Configure environment variable for backend origin; set up CORS-compatible fetch wrapper
    - _Requirements: 7.1, 7.4, 7.6_

  - [x] 11.2 Implement document upload UI component
    - Build upload form with drag-and-drop and file-picker; enforce 10 MB client-side size check
    - Display upload progress as percentage (0–100)
    - Show success notification on upload completion; show error notification with failure reason on failure
    - Display "no documents uploaded" empty state message
    - _Requirements: 6.1, 6.2, 6.8, 6.9, 6.12_

  - [x] 11.3 Implement document list UI component
    - Render list of uploaded documents showing filename, upload date, and file size
    - Fetch from `GET /documents` with pagination (10–100 items per page)
    - Show loading indicator while fetching; update list after successful upload or delete
    - _Requirements: 6.3, 6.7_

  - [x] 11.4 Implement chat interface UI component
    - Build chat input field limited to 2000 characters; display character count
    - Render chat messages in chronological order (most recent 100); preserve line breaks and paragraph structure in responses
    - Show loading indicator while waiting for API response
    - _Requirements: 6.4, 6.5, 6.6, 6.7_

  - [x] 11.5 Apply responsive design and visual polish
    - Implement responsive layouts for 320px (mobile), 768px (tablet), and 1024px+ (desktop) breakpoints
    - Apply clean typography and spacing following modern design principles
    - _Requirements: 6.10, 6.11_

  - [x] 11.6 Write React Testing Library unit tests for frontend components
    - Test document list rendering, chat message rendering, upload progress display, error and success notifications, responsive breakpoints
    - _Requirements: 6.2, 6.3, 6.4, 6.6, 6.8, 6.9, 6.11_

  - [x] 11.7 Write Playwright E2E tests for critical user flows
    - Full upload → query → response flow on desktop and mobile viewports
    - _Requirements: 6.1, 6.4, 6.5, 6.6_

- [x] 12. Docker health checks and service startup integration
  - [x] 12.1 Implement health check endpoints and startup validation
    - Verify Docker health check endpoints respond for Qdrant, MinIO, and PostgreSQL within 10 s interval / 5 s timeout
    - Implement `backend` service startup logic that waits for all three data services to report healthy before accepting traffic
    - Log startup failure and exit with non-zero code if any dependent service fails within 60 s
    - _Requirements: 8.5, 8.6, 8.7_

  - [x] 12.2 Write smoke test for Docker service health
    - Verify all services report healthy within 60 s after `docker compose up`
    - _Requirements: 8.5, 8.6, 8.7_

- [x] 13. Hypothesis test suite configuration
  - [x] 13.1 Set up Hypothesis test profile and conftest
    - Create `backend/tests/conftest.py` registering the `rag_pbt` settings profile (`max_examples=100`, `suppress_health_check=[HealthCheck.too_slow]`, `deadline=None`)
    - Add `# Feature: rag-chatbot-application, Property {N}: {property_text}` annotation to every property test
    - _Requirements: All property tests (P1–P29)_

- [x] 14. Final checkpoint — Ensure all tests pass
  - Run the full test suite (pytest for backend, vitest for frontend, Playwright for E2E). Ensure all tests pass. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP build
- Backend is Python (FastAPI + Hypothesis); frontend is TypeScript (React + Vitest + Playwright)
- All 29 correctness properties from the design are mapped to dedicated optional (`*`) property-based test sub-tasks
- Each task references specific requirements for full traceability
- Checkpoints at tasks 10 and 14 ensure incremental validation before moving to the next phase
- Property tests use `@settings(max_examples=100)` and are tagged with `# Feature: rag-chatbot-application, Property N`
- The 10 MB upload limit (Requirements 4.4, 7.1) is the enforced limit; the 50 MB reference in Requirement 1.9 is treated as a legacy value per the design

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "13.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "4.1"] },
    { "id": 4, "tasks": ["4.2", "5.1"] },
    { "id": 5, "tasks": ["4.3", "4.4", "4.5", "4.6", "5.2", "5.3", "5.4"] },
    { "id": 6, "tasks": ["5.5", "5.6", "5.7", "6.1"] },
    { "id": 7, "tasks": ["6.2", "6.3", "6.4", "7.1"] },
    { "id": 8, "tasks": ["7.2"] },
    { "id": 9, "tasks": ["7.3", "7.4", "7.5", "7.6", "7.7", "7.8", "7.9", "8.1"] },
    { "id": 10, "tasks": ["8.2", "8.3", "8.4", "8.5", "8.6", "8.7", "8.8", "9.1"] },
    { "id": 11, "tasks": ["9.2", "9.3", "9.4", "11.1"] },
    { "id": 12, "tasks": ["11.2", "11.3", "12.1"] },
    { "id": 13, "tasks": ["11.4", "12.2"] },
    { "id": 14, "tasks": ["11.5"] },
    { "id": 15, "tasks": ["11.6", "11.7"] }
  ]
}
```
