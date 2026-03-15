import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models.user import User
from models.agent import Agent
from models.agent_report import AgentReport
from models.conversation import Conversation
from schemas.chat import ChatRequest, ChatResponse
from utils.dependencies import get_current_user
from utils.agent_runner import run_agent as call_agent, stream_agent
from services.usage_service import UsageService


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["Chat"]
)

MAX_MESSAGE_LENGTH = 4000
MAX_REPORT_TITLE_LENGTH = 120
REPORT_TRIGGER_KEYWORDS = (
    "report",
    "analysis",
    "analyze",
    "research",
    "brief",
    "summary",
    "summarize",
    "market",
    "trends",
    "opportunities",
    "competitor",
    "startup idea",
    "seo",
    "sources",
)


def build_report_title(message: str) -> str:
    normalized = " ".join(message.split()).strip()
    if not normalized:
        return "Untitled report"
    if len(normalized) <= MAX_REPORT_TITLE_LENGTH:
        return normalized
    return f"{normalized[: MAX_REPORT_TITLE_LENGTH - 3].rstrip()}..."


def should_save_agent_report(message: str, content: str) -> bool:
    normalized_message = " ".join(message.lower().split())
    normalized_content = content.strip()
    normalized_content_lower = normalized_content.lower()

    if not normalized_content or len(normalized_content) < 180:
        return False

    keyword_match = any(keyword in normalized_message for keyword in REPORT_TRIGGER_KEYWORDS)
    structured_content = any(
        signal in normalized_content_lower
        for signal in ("\n#", "\n-", "\n*", "\n1.", "sources:", "summary:", "overview:", "key takeaways:")
    )
    paragraph_count = sum(1 for part in normalized_content.split("\n\n") if part.strip())

    return keyword_match or structured_content or paragraph_count >= 3


def save_agent_report(db: Session, agent_id: int, user_id: int, message: str, content: str) -> AgentReport | None:
    if not should_save_agent_report(message, content):
        return None

    try:
        report = AgentReport(
            agent_id=agent_id,
            user_id=user_id,
            title=build_report_title(message),
            content=content,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to save agent report: agent={agent_id} user={user_id}: {exc}", exc_info=True)
        return None


# ── Standard Response ─────────────────────────────────────────────────────────────
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

    # ── CHECK MESSAGE LIMIT FIRST ─────────────────────────────────────────────────
    allowed, reason = UsageService.check_can_send_message(db, current_user.id)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=reason)

    agent = db.query(Agent).filter(
        Agent.id == chat.agent_id,
        Agent.user_id == current_user.id,
    ).first()

    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent {chat.agent_id} not found.")

    conversation_history = db.query(Conversation).filter(
        Conversation.agent_id == chat.agent_id,
        Conversation.user_id == current_user.id,
    ).order_by(Conversation.created_at).all()

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

    ai_message = Conversation(agent_id=chat.agent_id, user_id=current_user.id, message=ai_response, role="assistant")
    db.add(ai_message)
    db.commit()
    db.refresh(ai_message)
    save_agent_report(db, chat.agent_id, current_user.id, message, ai_response)

    # ── RECORD USAGE AFTER SUCCESS ────────────────────────────────────────────────
    UsageService.record_message(db, current_user.id, agent_id=chat.agent_id)

    logger.info(f"Chat completed: agent={chat.agent_id} user={current_user.id} response_len={len(ai_response)}")
    return ai_message


# ── Streaming Response ────────────────────────────────────────────────────────────
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

    # ── CHECK MESSAGE LIMIT FIRST ─────────────────────────────────────────────────
    allowed, reason = UsageService.check_can_send_message(db, current_user.id)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=reason)

    agent = db.query(Agent).filter(
        Agent.id == chat.agent_id,
        Agent.user_id == current_user.id,
    ).first()

    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent {chat.agent_id} not found.")

    conversation_history = db.query(Conversation).filter(
        Conversation.agent_id == chat.agent_id,
        Conversation.user_id == current_user.id,
    ).order_by(Conversation.created_at).all()

    db.add(Conversation(agent_id=chat.agent_id, user_id=current_user.id, message=message, role="user"))
    db.commit()

    # ── CRITICAL FIX ──────────────────────────────────────────────────────────────
    # ALL SQLAlchemy ORM objects lose their session once StreamingResponse is returned.
    # Extract EVERYTHING as plain Python types before the session closes.
    user_id = current_user.id          # plain int
    agent_id = chat.agent_id           # plain int
    agent_config = dict(agent.config)  # plain dict

    # conversation_history is a list of ORM objects — also detaches after session closes
    # convert each to a plain dict so agent_runner can safely access .role and .message
    history_dicts = [
        {"role": h.role, "message": h.message}
        for h in conversation_history
    ]

    async def event_generator():
        full_response = []

        try:
            async for token in stream_agent(
                user_message=message,
                conversation_history=history_dicts,
                agent_config=agent_config,
            ):
                full_response.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"

            complete_response = "".join(full_response)

            # open a fresh DB session inside the generator to save the response
            # because the original session from Depends(get_db) is already closed
            from database import SessionLocal
            save_db = SessionLocal()
            try:
                ai_message = Conversation(
                    agent_id=agent_id,
                    user_id=user_id,
                    message=complete_response,
                    role="assistant",
                )
                save_db.add(ai_message)
                save_db.commit()
                save_db.refresh(ai_message)
                message_id = ai_message.id
                save_agent_report(save_db, agent_id, user_id, message, complete_response)
                
                # ── RECORD USAGE AFTER STREAMING COMPLETES ───────────────────────
                UsageService.record_message(save_db, user_id, agent_id=agent_id)
            finally:
                save_db.close()

            yield f"data: {json.dumps({'done': True, 'message_id': message_id, 'agent_id': agent_id})}\n\n"

            logger.info(
                f"Stream completed: agent={agent_id} user={user_id} "
                f"tokens={len(full_response)} chars={len(complete_response)}"
            )

        except Exception as e:
            logger.error(f"Stream failed: agent={agent_id} user={user_id}: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': 'Stream failed. Please try again.'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
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
