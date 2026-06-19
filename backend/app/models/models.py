"""
Shared Pydantic v2 models for the RAG Chatbot Application.

Covers: document metadata, chat sessions/messages, configuration,
upload/processing results, chat responses, and chunk representations.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    XLS = "xls"
    TXT = "txt"
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"


# ---------------------------------------------------------------------------
# Document models  (Requirements 2.9, 7.2)
# ---------------------------------------------------------------------------


class DocumentMetadata(BaseModel):
    """Metadata record stored in PostgreSQL for every uploaded document.

    All six required fields (document_id, filename, upload_timestamp,
    file_size, format, processing_status) are present and non-null.
    """

    document_id: UUID
    filename: str
    upload_timestamp: datetime
    file_size_bytes: int
    format: DocumentFormat
    processing_status: ProcessingStatus
    error_detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat session / message models  (Requirements 11.1, 11.2, 11.6)
# ---------------------------------------------------------------------------


class ChatSession(BaseModel):
    """A chat session created by Chat_Service.

    session_id is a UUID generated on session start (Requirement 11.1).
    """

    session_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    archived_at: Optional[datetime] = None


class ChatMessage(BaseModel):
    """A single message stored in the Metadata Store.

    timestamp is always set (Requirement 11.6).
    session_id links back to the owning ChatSession (Requirement 11.2).
    """

    message_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # Fields populated on assistant messages
    query_text: Optional[str] = None
    retrieved_chunk_ids: Optional[List[UUID]] = None
    reranking_scores: Optional[List[float]] = None
    reranking_provider: Optional[str] = None
    reranking_duration_ms: Optional[float] = None


# ---------------------------------------------------------------------------
# Chunk / retrieval models
# ---------------------------------------------------------------------------


class Chunk(BaseModel):
    """A text chunk produced by the Document Processor and indexed in Qdrant."""

    chunk_id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    chunk_text: str
    position_in_document: int
    contextual_summary: Optional[str] = None
    token_count: Optional[int] = None


class RankedChunk(BaseModel):
    """A chunk together with its reranking (or similarity) score.

    score is bounded to [0.0, 1.0] (Requirements 13.8, 10.1).
    """

    chunk: Chunk
    score: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Upload / processing result models  (Requirements 7.2, 2.9)
# ---------------------------------------------------------------------------


class UploadResult(BaseModel):
    """Returned by Upload Handler on a successful file upload (Requirement 7.2)."""

    document_id: UUID
    upload_timestamp: datetime
    filename: str
    file_size_bytes: int


class ProcessingResult(BaseModel):
    """Returned by Document Processor after processing completes or fails."""

    document_id: UUID
    status: ProcessingStatus
    error_detail: Optional[str] = None
    chunks_created: Optional[int] = None


# ---------------------------------------------------------------------------
# Chat response model  (Requirement 7.5)
# ---------------------------------------------------------------------------


class ChatResponse(BaseModel):
    """Response returned by Chat Service for a successful query (Requirement 7.5).

    Includes answer, retrieved_chunks, reranking_scores, and response_timestamp.
    """

    answer: str
    session_id: UUID
    retrieved_chunks: List[RankedChunk] = Field(default_factory=list)
    reranking_scores: List[float] = Field(default_factory=list)
    reranking_provider: Optional[str] = None
    reranking_duration_ms: Optional[float] = None
    response_timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Application configuration models
# ---------------------------------------------------------------------------


class PromptTemplates(BaseModel):
    system_instructions: str = (
        "You are a helpful assistant that answers questions based on the provided document context."
    )


class ChunkingConfig(BaseModel):
    chunk_size_tokens: int = Field(default=400, ge=300, le=500)
    overlap_percentage: float = Field(default=12.0, ge=10.0, le=15.0)
    enable_contextual_summaries: bool = True


class ModelConfig(BaseModel):
    llm_model_name: str = "openai/gpt-4o"
    llm_fallback_models: List[str] = Field(default_factory=list)
    embedding_model_name: str = "openai/text-embedding-3-small"


class RerankerConfig(BaseModel):
    reranker_provider: str = Field(default="cohere", pattern="^(cohere|jina)$")
    reranker_model_name: str = "rerank-english-v3.0"
    reranker_top_k: int = Field(default=5, ge=1, le=20)


class RetrievalConfig(BaseModel):
    top_k: int = Field(default=20, ge=1, le=50)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    max_chunks_evaluated: int = Field(default=100, ge=1)
    prompt_max_chars: int = Field(default=8000, ge=1000)


class AppConfig(BaseModel):
    """Full application configuration loaded and validated by Configuration Manager."""

    prompt_templates: PromptTemplates = Field(default_factory=PromptTemplates)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
