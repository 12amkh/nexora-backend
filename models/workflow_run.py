from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="completed")
    input = Column(Text, nullable=False)
    final_output = Column(Text, nullable=False, default="")
    steps = Column(JSON, nullable=False, default=list)
    error_message = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=func.now(), nullable=False)

    workflow = relationship("Workflow", back_populates="runs")
    user = relationship("User", back_populates="workflow_runs")

    def __repr__(self):
        return f"WorkflowRun(id={self.id}, workflow_id={self.workflow_id}, user_id={self.user_id}, status={self.status})"
