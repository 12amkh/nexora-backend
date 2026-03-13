# models/conversation.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id         = Column(Integer, primary_key=True, index=True)
    agent_id   = Column(Integer, ForeignKey("agents.id"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    message    = Column(String, nullable=False)
    role       = Column(String, nullable=False)  # "user" or "assistant"
    created_at = Column(DateTime, default=func.now())

    agent = relationship("Agent", back_populates="conversations")  # new

    def __repr__(self):
        return f"Conversation(id={self.id}, role={self.role})"