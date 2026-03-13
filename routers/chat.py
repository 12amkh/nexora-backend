# routers/chat.py

import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models.user import User
from models.agent import Agent
from models.conversation import Conversation
from schemas.chat import ChatRequest, ChatResponse
from utils.dependencies import get_current_user
from utils.agent_runner import run_agent as call_agent, stream_agent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["Chat"]
)

MAX_MESSAGE_LENGTH = 4000


# ── Standard Response ─────────────────────────────────────────────────────────────
# POST /chat/run — waits for full response, returns single JSON object
# best for: simple integrations, mobile apps, API clients
@router.post(
    "/run",
    response_model=ChatResponse,
    summary="Send a message and get a complete AI response (non-streaming)",
)
async def run_agent(
    chat: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = chat.message.strip()

    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty.")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Message too long. Max {MAX_MESSAGE_LENGTH} characters.")

    agent = db.query(Agent).filter(
        Agent.id == chat.agent_id,
        Agent.user_id == current_user.id,
    ).first()

    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent {chat.agent_id} not found.")

    # load history BEFORE saving new message — avoid sending it twice to LLM
    conversation_history = db.query(Conversation).filter(
        Conversation.agent_id == chat.agent_id,
        Conversation.user_id == current_user.id,
    ).order_by(Conversation.created_at).all()

    # save user message
    db.add(Conversation(agent_id=chat.agent_id, user_id=current_user.id, message=message, role="user"))
    db.commit()

    try:
        ai_response = await call_agent(
            user_message=message,
            conversation_history=conversation_history,
            agent_config=agent.config,
        )
    except Exception as e:
        logger.error(f"run_agent failed: agent={chat.agent_id} user={current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI agent encountered an error. Please try again.")

    # save and return AI response
    ai_message = Conversation(agent_id=chat.agent_id, user_id=current_user.id, message=ai_response, role="assistant")
    db.add(ai_message)
    db.commit()
    db.refresh(ai_message)

    logger.info(f"Chat completed: agent={chat.agent_id} user={current_user.id} response_len={len(ai_response)}")
    return ai_message


# ── Streaming Response ────────────────────────────────────────────────────────────
# POST /chat/stream — streams tokens via SSE as they're generated
# best for: web frontend, showing real-time typing effect
#
# SSE format — each line sent to client looks like:
#   data: {"token": "The"}
#   data: {"token": " latest"}
#   data: {"token": " news"}
#   data: {"done": true, "message_id": 42}
@router.post(
    "/stream",
    summary="Send a message and stream the AI response token by token (SSE)",
)
async def stream_response(
    chat: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = chat.message.strip()

    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty.")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Message too long. Max {MAX_MESSAGE_LENGTH} characters.")

    agent = db.query(Agent).filter(
        Agent.id == chat.agent_id,
        Agent.user_id == current_user.id,
    ).first()

    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent {chat.agent_id} not found.")

    # load history BEFORE saving new message
    conversation_history = db.query(Conversation).filter(
        Conversation.agent_id == chat.agent_id,
        Conversation.user_id == current_user.id,
    ).order_by(Conversation.created_at).all()

    # save user message
    db.add(Conversation(agent_id=chat.agent_id, user_id=current_user.id, message=message, role="user"))
    db.commit()

    # ── SSE Generator ─────────────────────────────────────────────────────────────
    # this is an async generator function — it yields SSE-formatted strings
    # FastAPI's StreamingResponse consumes this generator and sends each yield
    # to the client immediately without buffering
    async def event_generator():
        full_response = []  # collect all tokens to save complete response at end

        try:
            async for token in stream_agent(
                user_message=message,
                conversation_history=conversation_history,
                agent_config=agent.config,
            ):
                full_response.append(token)

                # format as SSE — "data: {json}\n\n" is the required SSE format
                # the double newline \n\n signals end of one SSE message
                yield f"data: {json.dumps({'token': token})}\n\n"

            # stream finished — save complete response to DB
            complete_response = "".join(full_response)

            ai_message = Conversation(
                agent_id=chat.agent_id,
                user_id=current_user.id,
                message=complete_response,
                role="assistant",
            )
            db.add(ai_message)
            db.commit()
            db.refresh(ai_message)

            # send final SSE event with message_id so client knows it's saved
            yield f"data: {json.dumps({'done': True, 'message_id': ai_message.id, 'agent_id': chat.agent_id})}\n\n"

            logger.info(
                f"Stream completed: agent={chat.agent_id} user={current_user.id} "
                f"tokens={len(full_response)} chars={len(complete_response)}"
            )

        except Exception as e:
            logger.error(f"Stream failed: agent={chat.agent_id} user={current_user.id}: {e}", exc_info=True)
            # send error event so client knows something went wrong
            yield f"data: {json.dumps({'error': 'Stream failed. Please try again.'})}\n\n"

    # StreamingResponse wraps our generator
    # media_type="text/event-stream" is required for SSE
    # headers tell browser/client not to cache the stream and to keep connection open
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",       # disables nginx buffering in production
            "Connection":        "keep-alive",
        },
    )


# ── Get History ───────────────────────────────────────────────────────────────────
@router.get(
    "/history/{agent_id}",
    response_model=List[ChatResponse],
    summary="Get paginated conversation history for an agent",
)
def get_history(
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip:  int = Query(default=0,  ge=0,  description="Number of messages to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Max messages to return"),
):
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.user_id == current_user.id,
    ).first()

    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent {agent_id} not found.")

    messages = db.query(Conversation).filter(
        Conversation.agent_id == agent_id,
        Conversation.user_id == current_user.id,
    ).order_by(Conversation.created_at).offset(skip).limit(limit).all()

    logger.info(f"History fetched: agent={agent_id} user={current_user.id} returned={len(messages)}")
    return messages