# Feature: rag-chatbot-application, Property 1: Supported file formats are always accepted
# Feature: rag-chatbot-application, Property 2: Unsupported file formats are always rejected
# Feature: rag-chatbot-application, Property 3: Files exceeding the size limit are always rejected
# Feature: rag-chatbot-application, Property 4: Successful uploads always return a unique document identifier
# Feature: rag-chatbot-application, Property 5: Empty files are always rejected
# Feature: rag-chatbot-application, Property 8: Document metadata records always contain all required fields

import asyncio
import io
import os
import uuid
from datetime import datetime
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from fastapi import UploadFile

from app.handlers.upload_handler import UploadHandler
from app.models.models import UploadResult, DocumentFormat

# ---------------------------------------------------------------------------
# Mock UploadHandler for testing validation logic without external services
# ---------------------------------------------------------------------------

class MockUploadHandler(UploadHandler):
    def __init__(self, *args, minio_fail=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.stored_files = []
        self.postgres_metadata = []
        self.minio_fail = minio_fail

    async def _store_in_minio(self, document_id: uuid.UUID, file_bytes: bytes, filename: str) -> None:
        if self.minio_fail:
            raise Exception("MinIO simulated storage failure")
        self.stored_files.append({
            "document_id": document_id,
            "file_bytes": file_bytes,
            "filename": filename
        })

    async def _write_metadata_to_postgres(
        self,
        document_id: uuid.UUID,
        filename: str,
        file_size: int,
        format: str,
    ) -> None:
        self.postgres_metadata.append({
            "document_id": document_id,
            "filename": filename,
            "file_size": file_size,
            "format": format
        })

# Helper to generate valid headers / content for various extensions
def make_valid_file_bytes(extension: str, size: int) -> bytes:
    if extension == ".pdf":
        prefix = b"%PDF-1.4"
    elif extension in {".jpg", ".jpeg"}:
        prefix = b"\xFF\xD8\xFF"
    elif extension == ".png":
        prefix = b"\x89PNG\r\n\x1a\n"
    elif extension in {".docx", ".xlsx", ".pptx"}:
        prefix = b"PK\x03\x04"
    else:  # .txt
        prefix = b""
    
    # Fill remaining bytes
    remaining = size - len(prefix)
    if remaining < 0:
        return prefix[:size]
    
    # Safe text/body content (avoid null bytes and executables headers)
    body = b"A" * remaining
    return prefix + body

# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

# Feature: rag-chatbot-application, Property 1: Supported file formats are always accepted
@given(
    extension=st.sampled_from([".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".txt", ".png", ".jpg", ".jpeg"]),
    size=st.integers(min_value=10, max_value=1024 * 1024)  # 10 bytes to 1 MB
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p1_supported_formats_accepted(extension: str, size: int) -> None:
    async def run():
        handler = MockUploadHandler()
        file_bytes = make_valid_file_bytes(extension, size)
        file_obj = io.BytesIO(file_bytes)
        upload_file = UploadFile(file=file_obj, filename=f"test_file{extension}")
        
        result = await handler.upload(upload_file)
        
        assert isinstance(result, UploadResult)
        assert result.filename == f"test_file{extension}"
        assert result.file_size_bytes == size
        assert len(handler.stored_files) == 1
        assert len(handler.postgres_metadata) == 1
        assert handler.postgres_metadata[0]["format"] == extension.lstrip(".").lower()

    asyncio.run(run())

# Feature: rag-chatbot-application, Property 2: Unsupported file formats are always rejected
@given(
    extension=st.text().filter(lambda x: x.lower() not in {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".txt", ".png", ".jpg", ".jpeg"}),
    size=st.integers(min_value=10, max_value=1000)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p2_unsupported_formats_rejected(extension: str, size: int) -> None:
    # Ensure it looks like a valid extension/filename and is not empty
    if not extension or not extension.startswith(".") or any(c in extension for c in "/\\?%*:|\"<> \x00"):
        return
    
    async def run():
        handler = MockUploadHandler()
        file_bytes = b"A" * size
        file_obj = io.BytesIO(file_bytes)
        upload_file = UploadFile(file=file_obj, filename=f"test_file{extension}")
        
        with pytest.raises(RuntimeError) as exc_info:
            await handler.upload(upload_file)
        
        assert exc_info.value.args[0] in {"unsupported_format", "invalid_file"}

    asyncio.run(run())

# Feature: rag-chatbot-application, Property 3: Files exceeding the size limit are always rejected
@given(
    extension=st.sampled_from([".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".txt", ".png", ".jpg", ".jpeg"]),
    oversize=st.integers(min_value=10 * 1024 * 1024 + 1, max_value=12 * 1024 * 1024)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p3_oversized_files_rejected(extension: str, oversize: int) -> None:
    async def run():
        handler = MockUploadHandler()
        file_bytes = make_valid_file_bytes(extension, oversize)
        file_obj = io.BytesIO(file_bytes)
        upload_file = UploadFile(file=file_obj, filename=f"test_file{extension}")
        
        with pytest.raises(RuntimeError) as exc_info:
            await handler.upload(upload_file)
        
        assert exc_info.value.args[0] == "file_too_large"

    asyncio.run(run())

# Feature: rag-chatbot-application, Property 4: Successful uploads always return a unique document identifier
def test_p4_unique_document_identifiers() -> None:
    async def run():
        handler = MockUploadHandler()
        ids = set()
        
        # Perform 50 successful uploads and check uniqueness
        for i in range(50):
            file_bytes = make_valid_file_bytes(".txt", 100)
            file_obj = io.BytesIO(file_bytes)
            upload_file = UploadFile(file=file_obj, filename=f"test_{i}.txt")
            result = await handler.upload(upload_file)
            assert result.document_id not in ids
            ids.add(result.document_id)
            
        assert len(ids) == 50

    asyncio.run(run())

# Feature: rag-chatbot-application, Property 5: Empty files are always rejected
@given(
    extension=st.sampled_from([".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".txt", ".png", ".jpg", ".jpeg"])
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p5_empty_files_rejected(extension: str) -> None:
    async def run():
        handler = MockUploadHandler()
        file_bytes = b""
        file_obj = io.BytesIO(file_bytes)
        upload_file = UploadFile(file=file_obj, filename=f"empty_file{extension}")
        
        with pytest.raises(RuntimeError) as exc_info:
            await handler.upload(upload_file)
            
        assert exc_info.value.args[0] == "invalid_file"

    asyncio.run(run())

# Feature: rag-chatbot-application, Property 8: Document metadata records always contain all required fields
@given(
    extension=st.sampled_from([".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".txt", ".png", ".jpg", ".jpeg"]),
    size=st.integers(min_value=10, max_value=1024 * 1024)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p8_metadata_completeness(extension: str, size: int) -> None:
    async def run():
        handler = MockUploadHandler()
        file_bytes = make_valid_file_bytes(extension, size)
        file_obj = io.BytesIO(file_bytes)
        upload_file = UploadFile(file=file_obj, filename=f"metadata_test{extension}")
        
        result = await handler.upload(upload_file)
        
        # Verify UploadResult
        assert isinstance(result.document_id, uuid.UUID)
        assert isinstance(result.upload_timestamp, datetime)
        assert result.filename == f"metadata_test{extension}"
        assert result.file_size_bytes == size
        
        # Verify stored PostgreSQL metadata
        assert len(handler.postgres_metadata) == 1
        meta = handler.postgres_metadata[0]
        assert isinstance(meta["document_id"], uuid.UUID)
        assert meta["filename"] == f"metadata_test{extension}"
        assert meta["file_size"] == size
        assert meta["format"] == extension.lstrip(".").lower()

    asyncio.run(run())

# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

def test_minio_storage_failure_path() -> None:
    async def run():
        # MinIO fails, handler should raise storage_failure and rollback postgres
        handler = MockUploadHandler(minio_fail=True)
        file_bytes = make_valid_file_bytes(".txt", 100)
        file_obj = io.BytesIO(file_bytes)
        upload_file = UploadFile(file=file_obj, filename="test.txt")
        
        with pytest.raises(RuntimeError) as exc_info:
            await handler.upload(upload_file)
            
        assert exc_info.value.args[0] == "storage_failure"
        assert len(handler.stored_files) == 0
        assert len(handler.postgres_metadata) == 0

    asyncio.run(run())
