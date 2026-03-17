from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class MarketplaceItem(Base):
    __tablename__ = "marketplace_items"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, unique=True, index=True)
    title = Column(String(120), nullable=False)
    description = Column(String(500), nullable=False)
    agent_type = Column(String(60), nullable=False, default="custom")
    config = Column(JSON, nullable=False, default={})
    is_published = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("User", back_populates="marketplace_items")
    source_agent = relationship("Agent", back_populates="marketplace_item")

    def __repr__(self):
        return f"MarketplaceItem(id={self.id}, owner_user_id={self.owner_user_id}, source_agent_id={self.source_agent_id})"
