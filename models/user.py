from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    """User model with usage tracking relationship."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    plan = Column(String, default="free")  # "free", "starter", "pro", "business", "enterprise"
    theme = Column(String, default="dark", nullable=False)  # "dark" or "light"
    theme_family = Column(String, default="nexora", nullable=False)  # selected palette family
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
 # ── PADDLE FIELDS ─────────────────────────────────────────────────────────────
    paddle_customer_id = Column(String, nullable=True, unique=True, index=True)
    paddle_subscription_id = Column(String, nullable=True, unique=True, index=True)
    paddle_subscription_status = Column(String, nullable=True)  # "active", "paused", "cancelled"
    paddle_subscription_started_at = Column(DateTime, nullable=True)
    paddle_subscription_next_billing_at = Column(DateTime, nullable=True)
    
    # Relationships
    agents = relationship("Agent", back_populates="user", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="user", cascade="all, delete-orphan")
    usage_metrics = relationship("UsageMetric", back_populates="user", cascade="all, delete-orphan")
    agent_reports = relationship("AgentReport", back_populates="user", cascade="all, delete-orphan")
    agent_memories = relationship("AgentMemory", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    marketplace_items = relationship("MarketplaceItem", back_populates="owner", cascade="all, delete-orphan")
    workflows = relationship("Workflow", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, plan={self.plan}, theme={self.theme}, theme_family={self.theme_family})>"
