# tasks/agent_tasks.py

import logging
import asyncio
from celery_app import celery_app
from database import SessionLocal
from models import Agent, Conversation, Schedule
from utils.agent_runner import run_agent
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)


# ── Run Agent Task ────────────────────────────────────────────────────────────────
# this is a Celery task — decorated with @celery_app.task
# it runs in a separate worker process, completely outside FastAPI
# can run for minutes without blocking anything
#
# bind=True gives us access to self (the task instance) for retries
# max_retries=3 — if it fails, retry up to 3 times automatically
# default_retry_delay=60 — wait 60 seconds between retries
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_scheduled_agent(self, schedule_id: int):
    """
    Background task that runs an agent automatically on a schedule.
    Called by Celery Beat at the scheduled time OR manually via API.

    Args:
        schedule_id: ID of the Schedule record to execute
    """
    logger.info(f"Starting scheduled agent run: schedule_id={schedule_id}")

    # create a fresh DB session — Celery workers are separate processes
    # they don't share the FastAPI DB session
    db = SessionLocal()

    try:
        # load the schedule
        schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()

        if not schedule:
            logger.error(f"Schedule {schedule_id} not found")
            return {"status": "failed", "error": "Schedule not found"}

        if not schedule.is_active:
            logger.info(f"Schedule {schedule_id} is paused — skipping")
            return {"status": "skipped", "reason": "Schedule is paused"}

        # load the agent
        agent = db.query(Agent).filter(Agent.id == schedule.agent_id).first()

        if not agent:
            logger.error(f"Agent {schedule.agent_id} not found for schedule {schedule_id}")
            return {"status": "failed", "error": "Agent not found"}

        # load conversation history for memory
        conversation_history = db.query(Conversation).filter(
            Conversation.agent_id == schedule.agent_id,
            Conversation.user_id == schedule.user_id,
        ).order_by(Conversation.created_at).all()

        # save the scheduled task message as a user message
        task_message = Conversation(
            agent_id=schedule.agent_id,
            user_id=schedule.user_id,
            message=schedule.task_message,
            role="user",
        )
        db.add(task_message)
        db.commit()

        # run the agent — asyncio.run() bridges sync Celery → async agent runner
        # Celery tasks are synchronous by default
        # asyncio.run() creates a new event loop just for this task
        ai_response = asyncio.run(
            run_agent(
                user_message=schedule.task_message,
                conversation_history=conversation_history,
                agent_config=agent.config,
            )
        )

        # save AI response
        ai_message = Conversation(
            agent_id=schedule.agent_id,
            user_id=schedule.user_id,
            message=ai_response,
            role="assistant",
        )
        db.add(ai_message)

        # update schedule with last run info
        schedule.last_run_at     = func.now()
        schedule.last_run_status = "success"

        db.commit()

        logger.info(
            f"Scheduled run complete: schedule={schedule_id} "
            f"agent={schedule.agent_id} response_len={len(ai_response)}"
        )

        return {
            "status":      "success",
            "schedule_id": schedule_id,
            "agent_id":    schedule.agent_id,
            "response_len": len(ai_response),
        }

    except Exception as e:
        logger.error(f"Scheduled run failed: schedule={schedule_id}: {e}", exc_info=True)

        # update schedule with failure status
        try:
            schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
            if schedule:
                schedule.last_run_at     = func.now()
                schedule.last_run_status = "failed"
                db.commit()
        except Exception:
            pass

        # retry the task automatically — self.retry() raises a special exception
        # that tells Celery to re-queue this task after default_retry_delay seconds
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for schedule {schedule_id}")
            return {"status": "failed", "error": str(e)}

    finally:
        db.close()  # always close the DB session
