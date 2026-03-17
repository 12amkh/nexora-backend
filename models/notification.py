from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True, index=True)
    report_id = Column(Integer, ForeignKey("agent_reports.id"), nullable=True, index=True)
    type = Column(String(50), nullable=False, default="report_ready")
    title = Column(String(200), nullable=False)
    message = Column(String(400), nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    read_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="notifications")
    agent = relationship("Agent", back_populates="notifications")
    report = relationship("AgentReport", back_populates="notifications")

    def __repr__(self):
        return f"Notification(id={self.id}, user_id={self.user_id}, type={self.type}, is_read={self.is_read})"
