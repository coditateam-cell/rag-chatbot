-- =============================================================================
-- RAG Chatbot Application — PostgreSQL Schema
-- =============================================================================
-- Requirement 2.9  : document_id, filename, upload_timestamp, file_size,
--                    format, processing_status must all be stored.
-- Requirements 11.1: chat_sessions stores session_id (UUID PK).
-- Requirements 11.2: chat_messages associates every query with a session_id.
-- Requirements 11.6: timestamp column is NOT NULL on every chat_messages row.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Documents table
-- Stores metadata for every uploaded document.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    document_id       UUID        PRIMARY KEY,
    filename          TEXT        NOT NULL,
    upload_timestamp  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    file_size_bytes   BIGINT      NOT NULL,
    format            TEXT        NOT NULL,   -- pdf | docx | pptx | xlsx | xls | txt | png | jpg | jpeg
    processing_status TEXT        NOT NULL DEFAULT 'pending',  -- pending | processing | completed | failed
    error_detail      TEXT,
    session_id        UUID
);

-- ---------------------------------------------------------------------------
-- Chat sessions table
-- One row per session created by Chat_Service (Requirement 11.1).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  UUID        PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- Chat messages table
-- Every user and assistant message is stored here (Requirements 11.2, 11.6).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id            UUID        PRIMARY KEY,
    session_id            UUID        NOT NULL REFERENCES chat_sessions(session_id),
    role                  TEXT        NOT NULL,   -- user | assistant
    content               TEXT        NOT NULL,
    timestamp             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    query_text            TEXT,
    retrieved_chunk_ids   UUID[],
    reranking_scores      FLOAT[],
    reranking_provider    TEXT,
    reranking_duration_ms FLOAT
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_documents_processing_status
    ON documents(processing_status);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id
    ON chat_messages(session_id);

CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp
    ON chat_messages(timestamp);
