from calendar import monthrange
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from core.plan_limits import get_plan_limit, normalize_plan
from models.user import User
from models.agent import Agent
from models.schedule import Schedule
from models.usage import UsageMetric
from typing import Dict, Tuple


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
        current_cycle_day = min(signup_day, monthrange(today.year, today.month)[1])

        # Users created near month-end keep a stable monthly cycle even in shorter months.
        if today.day >= current_cycle_day:
            month_start = UsageService._build_cycle_datetime(today.year, today.month, signup_day)
        else:
            previous_year, previous_month = UsageService._shift_month(today.year, today.month, -1)
            month_start = UsageService._build_cycle_datetime(previous_year, previous_month, signup_day)

        next_year, next_month = UsageService._shift_month(month_start.year, month_start.month, 1)
        month_end = UsageService._build_cycle_datetime(next_year, next_month, signup_day)
        return month_start, month_end

    @staticmethod
    def _build_cycle_datetime(year: int, month: int, preferred_day: int) -> datetime:
        # Clamp the billing anchor day to the last valid day of the target month.
        day = min(preferred_day, monthrange(year, month)[1])
        return datetime(year, month, day, 0, 0, 0, 0)

    @staticmethod
    def _shift_month(year: int, month: int, delta: int) -> Tuple[int, int]:
        # Shift by whole months without introducing external dependencies.
        absolute_month = (year * 12 + (month - 1)) + delta
        shifted_year = absolute_month // 12
        shifted_month = absolute_month % 12 + 1
        return shifted_year, shifted_month

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

        plan = normalize_plan(user.plan)
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
            "messages_limit": get_plan_limit(plan, "max_messages_per_month"),
            "messages_percent": UsageService._percent(messages_count, get_plan_limit(plan, "max_messages_per_month")),
            "agents_used": agents_count,
            "agents_limit": get_plan_limit(plan, "max_agents"),
            "agents_percent": UsageService._percent(agents_count, get_plan_limit(plan, "max_agents")),
            "schedules_used": schedules_count,
            "schedules_limit": get_plan_limit(plan, "max_schedules"),
            "schedules_percent": UsageService._percent(schedules_count, get_plan_limit(plan, "max_schedules")),
            "billing_month_start": month_start.isoformat(),
            "billing_month_end": month_end.isoformat(),
        }

    @staticmethod
    def _percent(used: int, limit: int | None) -> int:
        if limit is None:
            return 0
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

        plan = normalize_plan(user.plan)
        used = UsageService.get_current_month_usage(db, user_id, "message")
        message_limit = get_plan_limit(plan, "max_messages_per_month")

        if message_limit is not None and used >= message_limit:
            return False, f"Message limit reached ({used}/{message_limit})"

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

        plan = normalize_plan(user.plan)

        agent_count = (
            db.query(func.count(Agent.id))
            .filter(Agent.user_id == user_id)
            .scalar()
        )

        agent_limit = get_plan_limit(plan, "max_agents")
        if agent_limit is not None and agent_count >= agent_limit:
            return False, f"Agent limit reached ({agent_count}/{agent_limit})"

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

        plan = normalize_plan(user.plan)

        schedule_count = (
            db.query(func.count(Schedule.id))
            .filter(Schedule.user_id == user_id)
            .scalar()
        )

        schedule_limit = get_plan_limit(plan, "max_schedules")
        if schedule_limit is not None and schedule_count >= schedule_limit:
            return False, f"Schedule limit reached ({schedule_count}/{schedule_limit})"

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
