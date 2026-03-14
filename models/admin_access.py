from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from models.base import Base

class AdminAccess(Base):
    """
    Tracks which users have admin access.
    Separate table so we don't add is_admin boolean to User table.
    """
    __tablename__ = "admin_access"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    role = Column(String, default="admin")  # "admin", "moderator" (extensible)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Which admin granted this?
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    granted_by_user = relationship("User", foreign_keys=[granted_by])

    def __repr__(self):
        return f"<AdminAccess(user_id={self.user_id}, role={self.role})>"