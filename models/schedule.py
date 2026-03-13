# models/schedule.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Schedule(Base):
    __tablename__ = "schedules"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    agent_id    = Column(Integer, ForeignKey("agents.id"), nullable=False)

    # the message/task to run automatically on each trigger
    task_message = Column(String, nullable=False)

    # cron expression — defines when to run
    # examples:
    #   "0 9 * * 1"   = every Monday at 9am
    #   "0 8 * * *"   = every day at 8am
    #   "*/30 * * * *" = every 30 minutes
    cron        = Column(String, nullable=False)

    # human-readable name so user knows what this schedule does
    name        = Column(String, nullable=False)

    # active/paused — user can pause without deleting
    is_active   = Column(Boolean, default=True, nullable=False)

    # track when it last ran and what the result was
    last_run_at     = Column(DateTime, nullable=True)
    last_run_status = Column(String, nullable=True)  # "success" or "failed"

    created_at  = Column(DateTime, default=func.now())

    # relationships
    user  = relationship("User",  back_populates="schedules")
    agent = relationship("Agent", back_populates="schedules")

    def __repr__(self):
        return f"Schedule(id={self.id}, name={self.name}, cron={self.cron})"