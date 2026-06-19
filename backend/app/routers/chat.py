"""
chat.py — FastAPI router for chat session and query endpoints.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.models.models import ChatMessage, ChatResponse
from app.routers.deps import get_chat_service
from app.handlers.chat_service import ChatServiceError

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatQueryRequest(BaseModel):
    session_id: UUID
    query: str
    document_ids: Optional[List[UUID]] = None


@router.post("/session", status_code=201)
async def create_chat_session(chat_service = Depends(get_chat_service)):
    """Create a new chat session and return its unique identifier."""
    session_id = await chat_service.create_session()
    return {"session_id": session_id}


@router.post("/query", response_model=ChatResponse)
async def chat_query(
    request: ChatQueryRequest,
    chat_service = Depends(get_chat_service),
):
    """Processes a natural language query and generates a grounded response."""
    try:
        return await chat_service.query(
            session_id=request.session_id,
            user_query=request.query,
            document_ids=request.document_ids
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_session", "detail": str(exc)},
        )
    except ChatServiceError as exc:
        status_code = 503 if exc.error_code in {"api_unavailable", "response_failure"} else 400
        return JSONResponse(
            status_code=status_code,
            content={"error": exc.error_code, "detail": exc.detail},
        )


@router.get("/history", response_model=List[ChatMessage])
async def get_chat_history(
    session_id: UUID = Query(...),
    chat_service = Depends(get_chat_service),
):
    """Retrieves the history of chat interactions for the current session."""
    try:
        return await chat_service.get_history(session_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_session", "detail": str(exc)},
        )
