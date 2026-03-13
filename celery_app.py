# celery_app.py

import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Celery App ────────────────────────────────────────────────────────────────────
# broker  = Redis — where FastAPI sends tasks TO
# backend = Redis — where Celery stores task results
# both use the same Redis instance, different DB numbers (0 and 1)
celery_app = Celery(
    "nexora",
    broker=REDIS_URL,
    backend=REDIS_URL.replace("/0", "/1"),  # use DB 1 for results, DB 0 for broker
)

# ── Configuration ─────────────────────────────────────────────────────────────────
celery_app.conf.update(
    # serialization — use JSON for tasks and results (safe, readable)
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # timezone — important for scheduled tasks
    timezone="UTC",
    enable_utc=True,

    # task behavior
    task_track_started=True,        # track when task starts (not just queued/done)
    task_acks_late=True,            # only mark task as done AFTER it completes
                                    # prevents task loss if worker crashes mid-task
    worker_prefetch_multiplier=1,   # each worker takes one task at a time
                                    # prevents one worker hoarding all tasks

    # results
    result_expires=86400,           # keep results for 24 hours then auto-delete

    # where to find our tasks — Celery needs this to auto-discover them
    include=["tasks.agent_tasks"],
)