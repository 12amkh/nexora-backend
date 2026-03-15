from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class AgentReport(Base):
    __tablename__ = "agent_reports"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    agent = relationship("Agent", back_populates="reports")
    user = relationship("User", back_populates="agent_reports")

    def __repr__(self):
        return f"AgentReport(id={self.id}, agent_id={self.agent_id}, user_id={self.user_id})"
