# schemas/chat.py

from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import List, Optional


class ChatRequest(BaseModel):
    agent_id: int
    message:  str

    @field_validator("message")
    @classmethod
    def validate_message(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty.")
        if len(v) > 4000:
            raise ValueError("Message cannot exceed 4000 characters.")
        return v


class ChatResponse(BaseModel):
    id:         int
    message:    str
    role:       str
    agent_id:   int
    user_id:    int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationHistory(BaseModel):
    messages: List[ChatResponse]


# ── Streaming Schemas ─────────────────────────────────────────────────────────────
# used by POST /chat/stream SSE endpoint

class StreamChunk(BaseModel):
    # sent to client for each token as it arrives
    # token = the word/piece of text just generated
    # done = True signals the stream is finished
    token: Optional[str] = None
    done:  bool          = False


class StreamComplete(BaseModel):
    # sent as the final SSE event after stream ends
    # contains the full response and the saved DB record id
    full_response: str
    message_id:    int
    agent_id:      int