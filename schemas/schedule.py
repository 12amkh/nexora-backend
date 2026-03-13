# schemas/schedule.py

from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


# ── Cron Validator ────────────────────────────────────────────────────────────────
# cron format: "minute hour day month weekday"
# examples:
#   "0 9 * * 1"    = every Monday at 9am
#   "0 8 * * *"    = every day at 8am
#   "*/30 * * * *" = every 30 minutes
#   "0 0 * * *"    = every day at midnight
def validate_cron_expression(cron: str) -> str:
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError(
            "Invalid cron expression. Must have 5 parts: minute hour day month weekday. "
            "Example: '0 9 * * 1' = every Monday at 9am"
        )
    return cron.strip()


class ScheduleCreate(BaseModel):
    agent_id:     int
    name:         str
    task_message: str
    cron:         str
    is_active:    bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Schedule name cannot be empty.")
        if len(v) > 100:
            raise ValueError("Schedule name cannot exceed 100 characters.")
        return v

    @field_validator("task_message")
    @classmethod
    def validate_task_message(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Task message cannot be empty.")
        if len(v) > 4000:
            raise ValueError("Task message cannot exceed 4000 characters.")
        return v

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v):
        return validate_cron_expression(v)


class ScheduleUpdate(BaseModel):
    name:         Optional[str]  = None
    task_message: Optional[str]  = None
    cron:         Optional[str]  = None
    is_active:    Optional[bool] = None

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v):
        if v is not None:
            return validate_cron_expression(v)
        return v


class ScheduleResponse(BaseModel):
    id:              int
    user_id:         int
    agent_id:        int
    name:            str
    task_message:    str
    cron:            str
    is_active:       bool
    last_run_at:     Optional[datetime]
    last_run_status: Optional[str]
    created_at:      datetime

    model_config = {"from_attributes": True}


class ScheduleRunResponse(BaseModel):
    # returned when a schedule is triggered manually
    schedule_id: int
    task_id:     str   # Celery task ID — use to check status
    message:     str