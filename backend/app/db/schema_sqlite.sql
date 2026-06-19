-- =============================================================================
-- RAG Chatbot Application — SQLite Schema
-- =============================================================================

CREATE TABLE IF NOT EXISTS documents (
    document_id       TEXT PRIMARY KEY,
    filename          TEXT NOT NULL,
    upload_timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_size_bytes   INTEGER NOT NULL,
    format            TEXT NOT NULL,
    processing_status TEXT NOT NULL DEFAULT 'pending',
    error_detail      TEXT
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    archived_at DATETIME
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id            TEXT PRIMARY KEY,
    session_id            TEXT NOT NULL REFERENCES chat_sessions(session_id),
    role                  TEXT NOT NULL,
    content               TEXT NOT NULL,
    timestamp             DATETIME DEFAULT CURRENT_TIMESTAMP,
    query_text            TEXT,
    retrieved_chunk_ids   TEXT,
    reranking_scores      TEXT,
    reranking_provider    TEXT,
    reranking_duration_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_documents_processing_status ON documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);
