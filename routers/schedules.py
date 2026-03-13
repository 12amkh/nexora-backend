# routers/schedules.py

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models.user import User
from models.agent import Agent
from models.schedule import Schedule
from schemas.schedule import ScheduleCreate, ScheduleUpdate, ScheduleResponse, ScheduleRunResponse
from utils.dependencies import get_current_user
from tasks.agent_tasks import run_scheduled_agent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/schedules",
    tags=["Schedules"]
)

# ── Plan Schedule Limits ──────────────────────────────────────────────────────────
# free     → 0  schedules ($0/month)   — scheduling is a paid feature
# starter  → 3  schedules ($19/month)  — light automation
# pro      → 10 schedules ($49/month)  — serious automation
# business → 50 schedules ($149/month) — full automation platform
# this is one of the strongest upgrade incentives — "set it and forget it"
PLAN_SCHEDULE_LIMITS = {
    "free":     1,
    "starter":  3,
    "pro":      10,
    "business": 50,
}


def get_schedule_limit(plan: str) -> int:
    return PLAN_SCHEDULE_LIMITS.get(plan, 0)  # default to free (0) if unknown plan


# ── Create Schedule ───────────────────────────────────────────────────────────────
@router.post(
    "/create",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new scheduled agent run",
)
def create_schedule(
    schedule: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = get_schedule_limit(current_user.plan)

    # free users hit a hard wall — clear upgrade message
    if limit == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Scheduled runs are available on Starter, Pro, and Business plans. "
                "Upgrade from $19/month to automate your agents."
            ),
        )

    existing_count = db.query(Schedule).filter(Schedule.user_id == current_user.id).count()
    if existing_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You have reached the maximum number of schedules ({limit}) "
                f"for your {current_user.plan} plan. Please upgrade to create more."
            ),
        )

    agent = db.query(Agent).filter(
        Agent.id == schedule.agent_id,
        Agent.user_id == current_user.id,
    ).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {schedule.agent_id} not found.",
        )

    new_schedule = Schedule(
        user_id=current_user.id,
        agent_id=schedule.agent_id,
        name=schedule.name,
        task_message=schedule.task_message,
        cron=schedule.cron,
        is_active=schedule.is_active,
    )
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)

    logger.info(
        f"Schedule created: '{new_schedule.name}' (id={new_schedule.id}) "
        f"cron='{new_schedule.cron}' by user {current_user.id}"
    )
    return new_schedule


# ── List Schedules ────────────────────────────────────────────────────────────────
@router.get(
    "/list",
    response_model=List[ScheduleResponse],
    summary="List all schedules for the current user",
)
def list_schedules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip:  int = Query(default=0,  ge=0),
    limit: int = Query(default=10, ge=1, le=100),
):
    schedules = db.query(Schedule).filter(
        Schedule.user_id == current_user.id
    ).offset(skip).limit(limit).all()

    return schedules


# ── Get One Schedule ──────────────────────────────────────────────────────────────
@router.get(
    "/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Get a single schedule by ID",
)
def get_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.query(Schedule).filter(
        Schedule.id == schedule_id,
        Schedule.user_id == current_user.id,
    ).first()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found.",
        )
    return schedule


# ── Update Schedule ───────────────────────────────────────────────────────────────
@router.put(
    "/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Update a schedule",
)
def update_schedule(
    schedule_id: int,
    schedule_data: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.query(Schedule).filter(
        Schedule.id == schedule_id,
        Schedule.user_id == current_user.id,
    ).first()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found.",
        )

    if schedule_data.name is not None:
        schedule.name = schedule_data.name.strip()
    if schedule_data.task_message is not None:
        schedule.task_message = schedule_data.task_message.strip()
    if schedule_data.cron is not None:
        schedule.cron = schedule_data.cron
    if schedule_data.is_active is not None:
        schedule.is_active = schedule_data.is_active

    db.commit()
    db.refresh(schedule)

    logger.info(f"Schedule updated: id={schedule_id} by user {current_user.id}")
    return schedule


# ── Delete Schedule ───────────────────────────────────────────────────────────────
@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a schedule",
)
def delete_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.query(Schedule).filter(
        Schedule.id == schedule_id,
        Schedule.user_id == current_user.id,
    ).first()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found.",
        )

    name = schedule.name
    db.delete(schedule)
    db.commit()

    logger.info(f"Schedule deleted: '{name}' id={schedule_id} by user {current_user.id}")
    return {"message": f"Schedule '{name}' deleted successfully."}


# ── Manual Trigger ────────────────────────────────────────────────────────────────
@router.post(
    "/{schedule_id}/run",
    response_model=ScheduleRunResponse,
    summary="Manually trigger a schedule to run right now",
)
def trigger_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = db.query(Schedule).filter(
        Schedule.id == schedule_id,
        Schedule.user_id == current_user.id,
    ).first()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found.",
        )

    task = run_scheduled_agent.delay(schedule_id)

    logger.info(
        f"Schedule manually triggered: id={schedule_id} "
        f"task_id={task.id} by user {current_user.id}"
    )

    return ScheduleRunResponse(
        schedule_id=schedule_id,
        task_id=task.id,
        message=f"Schedule '{schedule.name}' is now running in the background. Check /chat/history/{schedule.agent_id} for results.",
    )


# ── Check Task Status ─────────────────────────────────────────────────────────────
@router.get(
    "/task/{task_id}",
    summary="Check the status of a background task",
)
def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    from celery_app import celery_app
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)

    return {
        "task_id": task_id,
        "status":  result.status,
        "result":  result.result if result.ready() else None,
    }