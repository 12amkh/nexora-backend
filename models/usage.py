from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from models.base import Base

class UsageMetric(Base):
    """
    Tracks user actions for usage limits.
    Each row = one action (message sent, agent created, schedule run).
    We query: count WHERE user_id=X AND metric_type=Y AND created_at >= month_start
    """
    __tablename__ = "usage_metrics"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    metric_type = Column(String, nullable=False)  # "message", "agent_created", "schedule_run"
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="usage_metrics")
    agent = relationship("Agent")

    # Indexes for fast queries
    __table_args__ = (
        Index("ix_usage_user_type_date", "user_id", "metric_type", "created_at"),
        Index("ix_usage_user_id", "user_id"),
    )

    def __repr__(self):
        return f"<UsageMetric(user_id={self.user_id}, type={self.metric_type}, created={self.created_at})>"