# models/agent.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Agent(Base):
    __tablename__ = "agents"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    name        = Column(String, nullable=False)
    description = Column(String, nullable=False)
    config      = Column(JSON, default={})
    created_at  = Column(DateTime, default=func.now())

    user          = relationship("User",  back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent")
    schedules     = relationship("Schedule", back_populates="agent")  # new
    reports       = relationship("AgentReport", back_populates="agent", cascade="all, delete-orphan")
    memory        = relationship("AgentMemory", back_populates="agent", uselist=False, cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="agent", cascade="all, delete-orphan")
    marketplace_item = relationship("MarketplaceItem", back_populates="source_agent", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"Agent(id={self.id}, name={self.name})"
