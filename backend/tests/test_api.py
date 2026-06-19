"""
test_api.py — Unit and integration tests for the FastAPI API layer.
"""

import os
import time
import uuid
import io
from datetime import datetime
from unittest.mock import MagicMock

# Set FRONTEND_ORIGIN in environment before importing app to configure CORSMiddleware
os.environ["FRONTEND_ORIGIN"] = "http://testfrontend.com"

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.routers.deps import get_db, get_minio_client, get_qdrant_client, get_document_processor
from app.models.models import DocumentMetadata


# ---------------------------------------------------------------------------
# In-Memory Database and Client Mocks for API Testing
# ---------------------------------------------------------------------------

class InMemDbSession:
    """Mock for PostgreSQL documents table in-memory."""

    def __init__(self) -> None:
        self.documents = {}
        self.committed = False

    async def execute(self, statement, params=None):
        stmt_str = str(statement).strip().replace("\n", " ").lower()

        class MockResult:
            def __init__(self, rows) -> None:
                self._rows = rows
            def fetchone(self):
                return self._rows[0] if self._rows else None
            def fetchall(self):
                return self._rows

        if "insert into documents" in stmt_str:
            doc_id = str(params["document_id"])
            self.documents[doc_id] = {
                "document_id": doc_id,
                "filename": params["filename"],
                "upload_timestamp": datetime.utcnow(),
                "file_size_bytes": params["file_size_bytes"],
                "format": params["format"],
                "processing_status": "pending",
                "error_detail": None,
            }
            return MockResult([])

        if "select filename, format" in stmt_str:
            doc_id = str(params["document_id"])
            if doc_id in self.documents:
                doc = self.documents[doc_id]
                return MockResult([(doc["filename"], doc["format"])])
            return MockResult([])

        if "select document_id" in stmt_str:
            rows = [
                (
                    uuid.UUID(doc["document_id"]),
                    doc["filename"],
                    doc["upload_timestamp"],
                    doc["file_size_bytes"],
                    doc["format"],
                    doc["processing_status"],
                    doc["error_detail"],
                )
                for doc in self.documents.values()
            ]
            rows.sort(key=lambda x: x[2], reverse=True)
            return MockResult(rows)

        if "select 1 from documents" in stmt_str:
            doc_id = str(params["document_id"])
            if doc_id in self.documents:
                return MockResult([(1,)])
            return MockResult([])

        if "update documents" in stmt_str:
            doc_id = str(params["document_id"])
            if doc_id in self.documents:
                self.documents[doc_id]["processing_status"] = params["status"]
                self.documents[doc_id]["error_detail"] = params["error_detail"]
            return MockResult([])

        if "delete from documents" in stmt_str:
            doc_id = str(params["document_id"])
            if doc_id in self.documents:
                del self.documents[doc_id]
            return MockResult([])

        return MockResult([])

    async def commit(self) -> None:
        self.committed = True


class MockMinioClient:
    """Mock for MinIO object storage."""

    def __init__(self) -> None:
        self.buckets = set()
        self.objects = {}

    def bucket_exists(self, bucket_name: str) -> bool:
        return bucket_name in self.buckets

    def make_bucket(self, bucket_name: str) -> None:
        self.buckets.add(bucket_name)

    def put_object(self, bucket_name: str, object_name: str, data, length: int, content_type: str) -> None:
        self.objects[object_name] = data.read()

    def get_object(self, bucket_name: str, object_name: str):
        if object_name not in self.objects:
            raise Exception("Object not found")

        class MockResponse:
            def __init__(self, data: bytes) -> None:
                self.data = data
            def read(self) -> bytes:
                return self.data
            def close(self) -> None:
                pass
            def release_conn(self) -> None:
                pass

        return MockResponse(self.objects[object_name])

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        if object_name in self.objects:
            del self.objects[object_name]


class MockQdrantClient:
    """Mock for Qdrant vector database."""

    def __init__(self) -> None:
        self.deleted_filters = []
        self.points = []

    def collection_exists(self, collection_name: str) -> bool:
        return True

    def create_collection(self, collection_name: str, vectors_config) -> None:
        pass

    def upsert(self, collection_name: str, points) -> None:
        self.points.extend(points)

    def delete(self, collection_name: str, points_selector) -> None:
        self.deleted_filters.append(points_selector)


# ---------------------------------------------------------------------------
# API Tests
# ---------------------------------------------------------------------------

def test_rate_limiting_middleware() -> None:
    """Validate rate limiter limits queries and returns HTTP 429 (Task 9.2)."""
    with TestClient(app) as client:
        # Clear rate limiter state for reproducibility
        if hasattr(app.state, "rate_limiter_requests"):
            app.state.rate_limiter_requests.clear()

        # Send 100 requests (all should pass)
        for _ in range(100):
            response = client.get("/")
            assert response.status_code == 200

        # 101st request must be rate limited
        response = client.get("/")
        assert response.status_code == 429
        assert response.json()["error"] == "rate_limit_exceeded"


def test_cors_origin_headers() -> None:
    """Validate CORS headers match frontend origin environment variable (Task 9.3)."""
    with TestClient(app) as client:
        # 1. Matching Origin
        response = client.get("/", headers={"Origin": "http://testfrontend.com"})
        assert response.headers.get("access-control-allow-origin") == "http://testfrontend.com"

        # 2. Non-matching Origin
        response = client.get("/", headers={"Origin": "http://maliciousorigin.com"})
        assert response.headers.get("access-control-allow-origin") is None


def test_document_lifecycle_integration() -> None:
    """Validate document upload -> list -> delete Lifecycle (Task 9.4)."""
    # Initialize in-memory dependencies
    db_session = InMemDbSession()
    minio_client = MockMinioClient()
    qdrant_client = MockQdrantClient()

    async def override_get_db():
        yield db_session

    def override_get_minio_client():
        return minio_client

    def override_get_qdrant_client():
        return qdrant_client

    from app.handlers.document_processor import DocumentProcessor
    from unittest.mock import AsyncMock, MagicMock
    from app.handlers.embedding_generator import EmbeddingGenerator

    mock_embedding_generator = AsyncMock(spec=EmbeddingGenerator)
    mock_embedding_generator.generate_embedding.return_value = [0.1] * 1536

    def override_get_document_processor():
        processor = DocumentProcessor(
            config_manager=app.state.config_manager,
            minio_client=minio_client,
            qdrant_client=qdrant_client,
            embedding_generator=mock_embedding_generator,
            db_session=db_session,
        )
        processor._parse_sync = MagicMock(return_value="Some parsed text content.")
        return processor

    # Apply overrides
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_minio_client] = override_get_minio_client
    app.dependency_overrides[get_qdrant_client] = override_get_qdrant_client
    app.dependency_overrides[get_document_processor] = override_get_document_processor

    with TestClient(app) as client:
        # Ensure rate limiter is clear
        if hasattr(app.state, "rate_limiter_requests"):
            app.state.rate_limiter_requests.clear()

        try:
            # 1. Upload Document
            # PDF file requires magic header %PDF
            file_content = b"%PDF-1.4\nSome text content"
            file_obj = io.BytesIO(file_content)
            
            response = client.post(
                "/documents/upload",
                files={"file": ("test_doc.pdf", file_obj, "application/pdf")}
            )
            assert response.status_code == 201
            data = response.json()
            assert "document_id" in data
            document_id = data["document_id"]
            assert "upload_timestamp" in data

            # Check in-memory stores are populated
            assert document_id in db_session.documents
            assert document_id in minio_client.objects

            # 2. List Documents
            response = client.get("/documents")
            assert response.status_code == 200
            docs_list = response.json()
            assert len(docs_list) == 1
            assert docs_list[0]["document_id"] == document_id
            assert docs_list[0]["filename"] == "test_doc.pdf"

            # 3. Delete Document
            response = client.delete(f"/documents/{document_id}")
            assert response.status_code == 200
            assert response.json()["status"] == "deleted"

            # Check database, MinIO and Qdrant deleted
            assert document_id not in db_session.documents
            assert document_id not in minio_client.objects
            assert len(qdrant_client.deleted_filters) == 1

            # Check list is now empty
            response = client.get("/documents")
            assert response.status_code == 200
            assert len(response.json()) == 0

        finally:
            # Clean overrides
            app.dependency_overrides.clear()
