from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from models.user import User
from models.agent import Agent
from models.schedule import Schedule
from models.usage import UsageMetric
from typing import Dict, Tuple

# Plan limits: (monthly_messages, total_agents, total_schedules)
PLAN_LIMITS = {
    "free": {
        "messages_per_month": 100,
        "agents_total": 3,
        "schedules_total": 0,
    },
    "starter": {
        "messages_per_month": 5000,
        "agents_total": 5,
        "schedules_total": 3,
    },
    "pro": {
        "messages_per_month": 50000,
        "agents_total": 20,
        "schedules_total": 10,
    },
    "business": {
        "messages_per_month": 500000,
        "agents_total": 100,
        "schedules_total": 50,
    },
    "enterprise": {
        "messages_per_month": 999999999,
        "agents_total": 999999999,
        "schedules_total": 999999999,
    },
}


class UsageService:
    """
    Manages usage tracking and plan limit enforcement.
    
    Billing cycle: Month-based on user's signup date.
    Example: If user signed up Jan 15, their monthly cycle is 15th of each month.
    """

    @staticmethod
    def get_billing_month_range(user: User) -> Tuple[datetime, datetime]:
        """
        Returns (month_start, month_end) for the current billing cycle.
        
        Billing cycle runs from signup_date day of month to same day next month.
        Example: signup Jan 15 → current cycle is from 15th to 14th (next month).
        """
        today = datetime.utcnow()
        signup_day = user.created_at.day

        # If today's day >= signup day, cycle started this month
        if today.day >= signup_day:
            month_start = today.replace(day=signup_day, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Cycle started last month
            if today.month == 1:
                month_start = datetime(today.year - 1, 12, signup_day)
            else:
                month_start = datetime(today.year, today.month - 1, signup_day)
            month_start = month_start.replace(hour=0, minute=0, second=0, microsecond=0)

        month_end = month_start + timedelta(days=30)
        return month_start, month_end

    @staticmethod
    def get_current_month_usage(db: Session, user_id: int, metric_type: str) -> int:
        """
        Count how many times metric_type occurred this billing month.
        metric_type: "message", "agent_created", "schedule_run"
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return 0

        month_start, month_end = UsageService.get_billing_month_range(user)

        count = (
            db.query(func.count(UsageMetric.id))
            .filter(
                UsageMetric.user_id == user_id,
                UsageMetric.metric_type == metric_type,
                UsageMetric.created_at >= month_start,
                UsageMetric.created_at < month_end,
            )
            .scalar()
        )
        return count or 0

    @staticmethod
    def get_usage_stats(db: Session, user_id: int) -> Dict:
        """
        Get current usage + limits for dashboard display.
        Returns dict with messages_used, agents_used, schedules_used, + limits.
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {}

        plan = user.plan or "free"
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
        month_start, month_end = UsageService.get_billing_month_range(user)

        # Count agents (total, not monthly reset)
        agents_count = (
            db.query(func.count(Agent.id))
            .filter(Agent.user_id == user_id)
            .scalar()
        )

        # Count schedules (total, not monthly reset)
        schedules_count = (
            db.query(func.count(Schedule.id))
            .filter(Schedule.user_id == user_id)
            .scalar()
        )

        # Count messages this month
        messages_count = UsageService.get_current_month_usage(db, user_id, "message")

        return {
            "plan": plan,
            "messages_used": messages_count,
            "messages_limit": limits["messages_per_month"],
            "messages_percent": UsageService._percent(messages_count, limits["messages_per_month"]),
            "agents_used": agents_count,
            "agents_limit": limits["agents_total"],
            "agents_percent": UsageService._percent(agents_count, limits["agents_total"]),
            "schedules_used": schedules_count,
            "schedules_limit": limits["schedules_total"],
            "schedules_percent": UsageService._percent(schedules_count, limits["schedules_total"]),
            "billing_month_start": month_start.isoformat(),
            "billing_month_end": month_end.isoformat(),
        }

    @staticmethod
    def _percent(used: int, limit: int) -> int:
        if limit <= 0:
            return 100 if used > 0 else 0
        return int((used / limit) * 100)

    @staticmethod
    def check_can_send_message(db: Session, user_id: int) -> Tuple[bool, str]:
        """
        Before sending a chat message, check if user has message capacity.
        Returns: (allowed: bool, reason: str)
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found"

        plan = user.plan or "free"
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
        used = UsageService.get_current_month_usage(db, user_id, "message")

        if used >= limits["messages_per_month"]:
            return False, f"Message limit reached ({used}/{limits['messages_per_month']})"

        return True, "OK"

    @staticmethod
    def check_can_create_agent(db: Session, user_id: int) -> Tuple[bool, str]:
        """
        Before creating an agent, check if user has agent capacity (total, not monthly).
        Returns: (allowed: bool, reason: str)
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found"

        plan = user.plan or "free"
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

        agent_count = (
            db.query(func.count(Agent.id))
            .filter(Agent.user_id == user_id)
            .scalar()
        )

        if agent_count >= limits["agents_total"]:
            return False, f"Agent limit reached ({agent_count}/{limits['agents_total']})"

        return True, "OK"

    @staticmethod
    def check_can_create_schedule(db: Session, user_id: int) -> Tuple[bool, str]:
        """
        Before creating a schedule, check if user has schedule capacity (total, not monthly).
        Returns: (allowed: bool, reason: str)
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, "User not found"

        plan = user.plan or "free"
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

        schedule_count = (
            db.query(func.count(Schedule.id))
            .filter(Schedule.user_id == user_id)
            .scalar()
        )

        if schedule_count >= limits["schedules_total"]:
            return False, f"Schedule limit reached ({schedule_count}/{limits['schedules_total']})"

        return True, "OK"

    @staticmethod
    def record_message(db: Session, user_id: int, agent_id: int = None):
        """Log that a user sent a message."""
        metric = UsageMetric(user_id=user_id, metric_type="message", agent_id=agent_id)
        db.add(metric)
        db.commit()

    @staticmethod
    def record_agent_created(db: Session, user_id: int, agent_id: int):
        """Log that a user created an agent."""
        metric = UsageMetric(user_id=user_id, metric_type="agent_created", agent_id=agent_id)
        db.add(metric)
        db.commit()

    @staticmethod
    def record_schedule_run(db: Session, user_id: int):
        """Log that a schedule was run (manually or via cron)."""
        metric = UsageMetric(user_id=user_id, metric_type="schedule_run")
        db.add(metric)
        db.commit()
