"""
Chat API endpoints for session management and query processing
"""
import secrets
import math
from typing import Dict, Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import get_db
from app.models.chat import ChatSession, Message, MessageRole
from app.schemas.chat import (
    CreateSessionRequest,
    SessionResponse,
    MessageResponse,
    SessionHistoryResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.genai.rag_service import RAGService, get_rag_service
import sys

# Create router
router = APIRouter()

# Initialize RAG service - use lazy initialization to avoid blocking on import
# In tests, this will be None and should be mocked
if 'pytest' not in sys.modules:
    rag_service = get_rag_service()
else:
    rag_service = None  # type: ignore  # Will be mocked in tests


def generate_session_token() -> str:
    """Generate a secure random session token"""
    return f"sess_{secrets.token_urlsafe(32)}"


def model_to_dict(model_instance) -> Dict[str, Any]:
    """Convert SQLAlchemy model instance to dictionary"""
    return {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in model_instance.__dict__.items()
        if not key.startswith("_")
    }


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Anonymous Chat Session",
    description="Create a new anonymous chat session with a unique session token"
)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db)
) -> SessionResponse:
    """
    Create a new anonymous chat session.

    - **metadata**: Optional metadata (IP address, user agent, etc.)

    Returns:
    - **id**: Session UUID
    - **session_token**: Unique session token for tracking
    - **created_at**: Session creation timestamp
    """
    try:
        # Generate unique session token
        session_token = generate_session_token()

        # Create new session (user_id is None for anonymous)
        session = ChatSession(
            session_token=session_token,
            user_id=None,  # Anonymous session
            meta=request.metadata or {}
        )

        db.add(session)
        await db.commit()
        await db.refresh(session)

        logger.info(f"Created new anonymous session: {session.id}")

        # Convert to response model
        return SessionResponse(
            id=str(session.id),
            session_token=session.session_token,
            user_id=None,
            created_at=session.created_at,
            updated_at=session.updated_at,
            metadata=session.meta
        )

    except Exception as e:
        logger.error(f"Error creating session: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session"
        )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionHistoryResponse,
    summary="Get Session History",
    description="Retrieve session information and message history with pagination"
)
async def get_session_history(
    session_id: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Messages per page"),
    db: AsyncSession = Depends(get_db)
) -> SessionHistoryResponse:
    """
    Retrieve session history with paginated messages.

    - **session_id**: Session UUID
    - **page**: Page number (default: 1)
    - **page_size**: Messages per page (default: 50, max: 100)

    Returns:
    - **session**: Session information
    - **messages**: List of messages (paginated)
    - **total_messages**: Total message count
    - **page**: Current page
    - **page_size**: Messages per page
    - **total_pages**: Total pages
    """
    try:
        # Parse UUID
        try:
            session_uuid = UUID(session_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session ID format"
            )

        # Fetch session
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == session_uuid)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )

        # Get total message count
        count_result = await db.execute(
            select(func.count(Message.id)).where(Message.session_id == session_uuid)
        )
        total_messages = count_result.scalar()

        # Calculate pagination
        total_pages = math.ceil(total_messages / page_size) if total_messages > 0 else 1
        offset = (page - 1) * page_size

        # Fetch paginated messages
        messages_result = await db.execute(
            select(Message)
            .where(Message.session_id == session_uuid)
            .order_by(Message.created_at.asc())
            .limit(page_size)
            .offset(offset)
        )
        messages = messages_result.scalars().all()

        # Convert to response models
        session_response = SessionResponse(
            id=str(session.id),
            session_token=session.session_token,
            user_id=str(session.user_id) if session.user_id else None,
            created_at=session.created_at,
            updated_at=session.updated_at,
            metadata=session.meta
        )

        message_responses = [
            MessageResponse(
                id=str(msg.id),
                session_id=str(msg.session_id),
                role=msg.role.value,
                content=msg.content,
                created_at=msg.created_at,
                sources=msg.sources,
                feedback=msg.feedback
            )
            for msg in messages
        ]

        return SessionHistoryResponse(
            session=session_response,
            messages=message_responses,
            total_messages=total_messages,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session history"
        )



@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Submit Query",
    description="Submit a query and get an AI-generated response with sources"
)
async def submit_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db)
) -> QueryResponse:
    """
    Submit a query to the RAG system and get a response.

    - **session_id**: Session UUID
    - **query**: User query text (1-2000 characters)
    - **source_type**: Optional source type filter
    - **temperature**: Optional LLM temperature (0.0-2.0)
    - **max_tokens**: Optional max tokens (50-4000)

    Returns:
    - **session_id**: Session UUID
    - **user_message**: User message that was saved
    - **assistant_message**: Assistant response with sources
    - **query_analysis**: Query analysis metadata
    """
    try:
        # Validate session exists
        try:
            session_uuid = UUID(request.session_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session ID format"
            )

        result = await db.execute(
            select(ChatSession).where(ChatSession.id == session_uuid)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )

        # Save user message
        user_message = Message(
            session_id=session_uuid,
            role=MessageRole.USER,
            content=request.query,
            sources=None,
            feedback=None
        )
        db.add(user_message)
        await db.commit()
        await db.refresh(user_message)

        logger.info(f"Saved user message for session {session_uuid}: {request.query[:50]}...")

        # Generate RAG response
        full_response = ""
        sources = {}
        query_analysis = {}

        async for chunk in rag_service.generate_rag_response(
            db=db,
            query=request.query,
            source_type=request.source_type,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        ):
            if chunk["type"] == "metadata":
                stage = chunk.get("stage", "")
                if stage == "query_analysis":
                    query_analysis = chunk["data"]
                elif stage == "sources":
                    sources = chunk["data"]
            elif chunk["type"] == "token":
                full_response += chunk["data"]

        # Save assistant message
        assistant_message = Message(
            session_id=session_uuid,
            role=MessageRole.ASSISTANT,
            content=full_response,
            sources=sources,
            feedback=None
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        logger.info(f"Saved assistant response for session {session_uuid}")

        # Update session timestamp
        session.updated_at = assistant_message.created_at
        await db.commit()

        # Build response
        return QueryResponse(
            session_id=str(session_uuid),
            user_message=MessageResponse(
                id=str(user_message.id),
                session_id=str(user_message.session_id),
                role=user_message.role.value,
                content=user_message.content,
                created_at=user_message.created_at,
                sources=user_message.sources,
                feedback=user_message.feedback
            ),
            assistant_message=MessageResponse(
                id=str(assistant_message.id),
                session_id=str(assistant_message.session_id),
                role=assistant_message.role.value,
                content=assistant_message.content,
                created_at=assistant_message.created_at,
                sources=assistant_message.sources,
                feedback=assistant_message.feedback
            ),
            query_analysis=query_analysis
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}"
        )



@router.websocket("/stream")
async def chat_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat streaming.

    Message types sent to client:
    - **start**: {"type": "start", "message": "Starting response generation"}
    - **token**: {"type": "token", "data": "word"}
    - **source**: {"type": "source", "data": {...}}
    - **complete**: {"type": "complete", "message": "Response generation complete"}
    - **error**: {"type": "error", "message": "Error description"}

    Client sends:
    - {"session_id": "uuid", "query": "question", "source_type": "optional", "temperature": 0.7, "max_tokens": 500}
    """
    await websocket.accept()
    logger.info("WebSocket connection established")

    try:
        # Receive query from client
        data = await websocket.receive_json()

        session_id = data.get("session_id")
        query = data.get("query")
        source_type = data.get("source_type")
        temperature = data.get("temperature")
        max_tokens = data.get("max_tokens")

        if not session_id or not query:
            await websocket.send_json({
                "type": "error",
                "message": "Missing required fields: session_id and query"
            })
            await websocket.close(code=1008)
            return

        # Validate session
        from app.db.session import async_session_maker
        async with async_session_maker() as db:
            try:
                session_uuid = UUID(session_id)
            except ValueError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid session ID format"
                })
                await websocket.close(code=1008)
                return

            result = await db.execute(
                select(ChatSession).where(ChatSession.id == session_uuid)
            )
            session = result.scalar_one_or_none()

            if not session:
                await websocket.send_json({
                    "type": "error",
                    "message": "Session not found"
                })
                await websocket.close(code=1008)
                return

            # Save user message
            user_message = Message(
                session_id=session_uuid,
                role=MessageRole.USER,
                content=query,
                sources=None,
                feedback=None
            )
            db.add(user_message)
            await db.commit()
            await db.refresh(user_message)

            logger.info(f"WebSocket: Saved user message for session {session_uuid}")

            # Send start message
            await websocket.send_json({
                "type": "start",
                "message": "Starting response generation"
            })

            # Stream RAG response
            full_response = ""
            sources = {}
            query_analysis = {}

            async for chunk in rag_service.generate_rag_response(
                db=db,
                query=query,
                source_type=source_type,
                temperature=temperature,
                max_tokens=max_tokens
            ):
                if chunk["type"] == "metadata":
                    stage = chunk.get("stage", "")
                    if stage == "query_analysis":
                        query_analysis = chunk["data"]
                    elif stage == "sources":
                        sources = chunk["data"]
                        # Send sources to client
                        await websocket.send_json({
                            "type": "source",
                            "data": sources
                        })
                elif chunk["type"] == "token":
                    full_response += chunk["data"]
                    # Send token to client
                    await websocket.send_json({
                        "type": "token",
                        "data": chunk["data"]
                    })

            # Save assistant message
            assistant_message = Message(
                session_id=session_uuid,
                role=MessageRole.ASSISTANT,
                content=full_response,
                sources=sources,
                feedback=None
            )
            db.add(assistant_message)
            await db.commit()
            await db.refresh(assistant_message)

            logger.info(f"WebSocket: Saved assistant response for session {session_uuid}")

            # Update session timestamp
            session.updated_at = assistant_message.created_at
            await db.commit()

            # Send completion message
            await websocket.send_json({
                "type": "complete",
                "message": "Response generation complete",
                "message_id": str(assistant_message.id)
            })

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed by client")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Internal error: {str(e)}"
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
        logger.info("WebSocket connection terminated")

