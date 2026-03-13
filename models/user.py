# models/user.py

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    email      = Column(String, unique=True, nullable=False)
    password   = Column(String, nullable=False)
    name       = Column(String, nullable=False)
    plan       = Column(String, default="free")
    created_at = Column(DateTime, default=func.now())

    agents        = relationship("Agent",        back_populates="user")
    schedules     = relationship("Schedule",     back_populates="user")  # new

    def __repr__(self):
        return f"User(id={self.id}, email={self.email})"