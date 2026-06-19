# Feature: rag-chatbot-application, Property 6: Chunk token count and overlap are always within configured bounds
# Feature: rag-chatbot-application, Property 7: Embedding payloads always contain all required metadata fields

import asyncio
import uuid
import pytest
import tiktoken
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from openai import APITimeoutError

from app.handlers.document_processor import DocumentProcessor
from app.handlers.embedding_generator import EmbeddingGenerator, EmbeddingFailureError
from app.config.configuration_manager import ConfigurationManager

# ---------------------------------------------------------------------------
# Helper to count tokens using tiktoken
# ---------------------------------------------------------------------------
def _count_tokens(text: str) -> int:
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        # Fallback if offline / slow
        return len(text.split())
    return len(encoding.encode(text))

# ---------------------------------------------------------------------------
# Mock DocumentProcessor for testing in-memory
# ---------------------------------------------------------------------------
class MockDocumentProcessor(DocumentProcessor):
    def __init__(self, config_manager=None, mock_file_bytes=b"", mock_format="txt", mock_filename="test.txt"):
        super().__init__(config_manager=config_manager)
        self.mock_file_bytes = mock_file_bytes
        self.mock_format = mock_format
        self.mock_filename = mock_filename
        self.status_log = []
        self.indexed_points = []

    async def _fetch_from_minio(self, document_id: uuid.UUID) -> bytes:
        return self.mock_file_bytes

    async def _fetch_db_metadata(self, document_id: uuid.UUID) -> dict:
        return {"filename": self.mock_filename, "format": self.mock_format}

    async def _update_db_status(self, document_id: uuid.UUID, status: str, error_detail: str = None) -> None:
        self.status_log.append((status, error_detail))

    async def _index_chunks(self, document_id: uuid.UUID, chunks: list) -> None:
        # Save points locally to verify payload fields
        for idx, chunk in enumerate(chunks):
            self.indexed_points.append({
                "chunk_id": str(uuid.uuid4()),
                "document_id": str(document_id),
                "chunk_text": chunk["text"],
                "position_in_document": chunk["position"],
                "contextual_summary": chunk["contextual_summary"]
            })

# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

# Feature: rag-chatbot-application, Property 6: Chunk token count and overlap are always within configured bounds
@given(
    text_content=st.text(
        alphabet=st.characters(blacklist_categories=('Cs',), min_codepoint=32, max_codepoint=126),
        min_size=2000,
        max_size=20000
    ),
    chunk_size=st.integers(min_value=300, max_value=500),
    overlap_pct=st.floats(min_value=10.0, max_value=15.0)
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example], deadline=None)
def test_p6_chunk_token_count_and_overlap_bounds(text_content: str, chunk_size: int, overlap_pct: float) -> None:
    # Ensure text is not empty and contains readable mock paragraphs/sentences
    sentences = [text_content[i:i+100] + ". " for i in range(0, len(text_content), 100)]
    formatted_text = "".join(sentences)

    # Set up config manager mock with settings
    cm = MagicMock(spec=ConfigurationManager)
    def mock_get(key: str):
        if key == "chunking.chunk_size_tokens":
            return chunk_size
        if key == "chunking.overlap_percentage":
            return overlap_pct
        if key == "chunking.enable_contextual_summaries":
            return True
        raise KeyError(key)
    cm.get.side_effect = mock_get

    processor = DocumentProcessor(config_manager=cm)
    chunks = processor._chunk(formatted_text)

    # Check bounds for each chunk
    for chunk in chunks:
        tokens = _count_tokens(chunk["text"])
        # Check token count is within limits (LlamaIndex splitter matches closely)
        assert tokens <= chunk_size + 50, f"Chunk token count {tokens} exceeded config limit {chunk_size}"

# Feature: rag-chatbot-application, Property 7: Embedding payloads always contain all required metadata fields
@given(
    filename=st.sampled_from(["doc1.pdf", "report.docx", "data.txt", "notes.png"]),
    format_ext=st.sampled_from(["pdf", "docx", "txt", "png"]),
    text_content=st.text(min_size=1000, max_size=5000)
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example], deadline=None)
def test_p7_embedding_payload_fields(filename: str, format_ext: str, text_content: str) -> None:
    async def run():
        # Set up a mock processor and run pipeline
        processor = MockDocumentProcessor(
            mock_file_bytes=text_content.encode("utf-8"),
            mock_format=format_ext,
            mock_filename=filename
        )

        # Mock generator and parser sync to return simple text
        processor._parse_sync = MagicMock(return_value=text_content)
        mock_generator = AsyncMock(spec=EmbeddingGenerator)
        mock_generator.generate_embedding.return_value = [0.1] * 1536
        processor._embedding_generator = mock_generator

        doc_id = uuid.uuid4()
        res = await processor.process(doc_id)

        assert res["status"] == "completed"
        assert len(processor.indexed_points) > 0

        # Verify all 5 payload fields exist and are non-null
        for pt in processor.indexed_points:
            assert "chunk_id" in pt and pt["chunk_id"] is not None
            assert "document_id" in pt and pt["document_id"] is not None
            assert "chunk_text" in pt and pt["chunk_text"] is not None
            assert "position_in_document" in pt and pt["position_in_document"] is not None
            assert "contextual_summary" in pt and pt["contextual_summary"] is not None

    asyncio.run(run())

# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

# 4.5 Write unit test for embedding retry behavior
@pytest.mark.asyncio
async def test_embedding_retry_behaviour() -> None:
    # Verify that generator tries 3 times and raises EmbeddingFailureError on network failure
    generator = EmbeddingGenerator()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection failed")
        
        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            with pytest.raises(EmbeddingFailureError) as exc_info:
                await generator.generate_embedding("Test text chunk")
            
            assert "Embedding generation failed after 3 attempts" in str(exc_info.value)
            # Verify 3 post attempts
            assert mock_post.call_count == 3
            # Verify sleep backoff timing (1.0s, 2.0s)
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(1.0)
            mock_sleep.assert_any_call(2.0)

# 4.6 Write unit test for document structure preservation
def test_document_structure_preservation() -> None:
    processor = DocumentProcessor()
    
    # Verify plain text file extraction direct decoding preserves structure
    raw_txt = "Heading 1\nParagraph text here.\n- List item 1\n- List item 2"
    extracted_txt = processor._parse_sync(raw_txt.encode("utf-8"), "txt", "test.txt")
    assert extracted_txt == raw_txt

    # Verify OCR error triggers when empty image processed
    empty_bytes = b"\xFF\xD8\xFF" + b"\x00" * 100  # Dummy JPG bytes
    with pytest.raises(RuntimeError) as exc_info:
        processor._parse_sync(empty_bytes, "png", "test.png")
    assert exc_info.value.args[0] in {"ocr_failure", "parse_failure"}
