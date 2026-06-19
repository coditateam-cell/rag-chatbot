"""
deps.py — FastAPI dependencies for RAG API routers.
"""

import os
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client import QdrantClient
from minio import Minio

from app.config.configuration_manager import ConfigurationManager
from app.db.connection import get_db
from app.handlers.upload_handler import UploadHandler
from app.handlers.document_processor import DocumentProcessor
from app.handlers.chat_service import ChatService


def get_config_manager(request: Request) -> ConfigurationManager:
    """Retrieves active ConfigurationManager from app.state."""
    return request.app.state.config_manager


# Lazy-loaded database clients for reuse across dependencies
_qdrant_client = None
_minio_client = None


def get_qdrant_client() -> QdrantClient:
    """Lazy-load Qdrant client. Supports both self-hosted and Qdrant Cloud."""
    global _qdrant_client
    if _qdrant_client is None:
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        if qdrant_url:
            # Qdrant Cloud managed service
            _qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        else:
            # Self-hosted (local Docker)
            host = os.getenv("QDRANT_HOST", "qdrant")
            port = int(os.getenv("QDRANT_PORT", "6333"))
            _qdrant_client = QdrantClient(host=host, port=port)
    return _qdrant_client


def get_minio_client() -> Minio:
    """Lazy-load MinIO client."""
    global _minio_client
    if _minio_client is None:
        host = os.getenv("MINIO_HOST", "minio")
        port = os.getenv("MINIO_PORT", "9000")
        access_key = os.getenv("MINIO_ROOT_USER", "minioadmin")
        secret_key = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
        _minio_client = Minio(
            f"{host}:{port}",
            access_key=access_key,
            secret_key=secret_key,
            secure=False,
        )
    return _minio_client


def get_upload_handler(
    config_manager: ConfigurationManager = Depends(get_config_manager),
    db_session: AsyncSession = Depends(get_db),
    minio_client = Depends(get_minio_client),
) -> UploadHandler:
    """Creates UploadHandler instance."""
    return UploadHandler(
        config_manager=config_manager,
        minio_client=minio_client,
        db_session=db_session,
    )


def get_document_processor(
    config_manager: ConfigurationManager = Depends(get_config_manager),
    minio_client = Depends(get_minio_client),
    qdrant_client = Depends(get_qdrant_client),
) -> DocumentProcessor:
    """Creates DocumentProcessor instance."""
    return DocumentProcessor(
        config_manager=config_manager,
        minio_client=minio_client,
        qdrant_client=qdrant_client,
    )


def get_chat_service(
    config_manager: ConfigurationManager = Depends(get_config_manager),
    db_session: AsyncSession = Depends(get_db),
) -> ChatService:
    """Creates ChatService instance."""
    return ChatService(
        config_manager=config_manager,
        db_session=db_session,
    )
