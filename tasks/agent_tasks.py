# tasks/agent_tasks.py

import logging
import asyncio
from copy import deepcopy
from celery_app import celery_app
from database import SessionLocal
from models import Agent, Conversation, Schedule
from utils.agent_runner import run_agent
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)


def build_scheduled_agent_config(agent_config: dict | None) -> dict:
    """
    Scheduled runs should behave more like brief digests than open-ended chat.
    We keep them concise by default to reduce token usage and make automations
    feel more useful in the product.
    """
    config = deepcopy(agent_config or {})
    existing_instructions = config.get("instructions", "").strip()
    scheduled_instruction = (
        "This is an automated scheduled run. Respond with a concise, scannable update. "
        "Prefer short summaries and bullet points where helpful. "
        "Only go long if the user's task explicitly asks for detailed output."
    )

    config["instructions"] = (
        f"{existing_instructions}\n\n{scheduled_instruction}"
        if existing_instructions
        else scheduled_instruction
    )

    response_length = config.get("response_length")
    if response_length not in {"short", "medium"}:
        config["response_length"] = "short"

    return config


def is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "rate_limit_exceeded" in text
        or "rate limit" in text
        or "too many requests" in text
        or "httpstatuserror" in exc.__class__.__name__.lower() and "429" in text
        or exc.__class__.__name__ == "RateLimitError"
    )


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
                agent_config=build_scheduled_agent_config(agent.config),
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
            "response":    ai_response,
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

        if is_rate_limit_error(e):
            logger.warning(f"Schedule {schedule_id} hit AI rate limits; skipping retry")
            return {
                "status": "failed",
                "error": "AI quota reached. Please try again later or reduce scheduled response size.",
            }

        # retry the task automatically — self.retry() raises a special exception
        # that tells Celery to re-queue this task after default_retry_delay seconds
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for schedule {schedule_id}")
            return {"status": "failed", "error": str(e)}

    finally:
        db.close()  # always close the DB session
