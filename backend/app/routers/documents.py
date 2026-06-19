"""
documents.py — FastAPI router for document metadata and file handling.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.models.models import DocumentMetadata
from app.routers.deps import (
    get_upload_handler,
    get_document_processor,
    get_minio_client,
    get_qdrant_client,
)
from app.db.connection import get_db

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    upload_handler = Depends(get_upload_handler),
    doc_processor = Depends(get_document_processor),
):
    """Uploads a document file and schedules its parsing/indexing asynchronously."""
    try:
        result = await upload_handler.upload(file)
        # Run parsing and chunk processing asynchronously in the background
        background_tasks.add_task(doc_processor.process, result.document_id)
        return {
            "document_id": result.document_id,
            "upload_timestamp": result.upload_timestamp.isoformat(),
        }
    except RuntimeError as exc:
        if len(exc.args) == 2:
            error_code, detail = exc.args[0], exc.args[1]
            status_code = 503 if error_code == "storage_failure" else 400
            return JSONResponse(
                status_code=status_code,
                content={"error": error_code, "detail": detail},
            )
        raise exc


@router.get("", response_model=List[DocumentMetadata])
async def list_documents(
    limit: int = Query(10, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db = Depends(get_db),
):
    """Retrieve a list of uploaded documents with pagination."""
    stmt = text(
        """
        SELECT document_id, filename, upload_timestamp, file_size_bytes, format, processing_status, error_detail
        FROM documents
        ORDER BY upload_timestamp DESC
        LIMIT :limit OFFSET :offset
        """
    )
    res = await db.execute(stmt, {"limit": limit, "offset": offset})
    rows = res.fetchall()

    docs = []
    for r in rows:
        docs.append(
            DocumentMetadata(
                document_id=r[0],
                filename=r[1],
                upload_timestamp=r[2],
                file_size_bytes=r[3],
                format=r[4],
                processing_status=r[5],
                error_detail=r[6],
            )
        )
    return docs


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    db = Depends(get_db),
    minio_client = Depends(get_minio_client),
    qdrant_client = Depends(get_qdrant_client),
):
    """Deletes a document from metadata store, object storage, and vector store."""
    # 1. Check if document exists
    stmt_check = text("SELECT 1 FROM documents WHERE document_id = :document_id")
    res_check = await db.execute(stmt_check, {"document_id": str(document_id)})
    if not res_check.fetchone():
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "detail": f"Document '{document_id}' not found.",
            },
        )

    # 2. Delete from PostgreSQL
    stmt_del = text("DELETE FROM documents WHERE document_id = :document_id")
    await db.execute(stmt_del, {"document_id": str(document_id)})
    await db.commit()

    # 3. Delete from MinIO
    try:
        minio_client.remove_object("documents", str(document_id))
    except Exception:
        # Log and proceed since it's already removed from the metadata store
        pass

    # 4. Delete associated embedding chunks from Qdrant
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        qdrant_client.delete(
            collection_name="document_chunks",
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=str(document_id)),
                    )
                ]
            ),
        )
    except Exception:
        pass

    return {"status": "deleted", "document_id": document_id}
