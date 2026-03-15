from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from models.user import User
from models.admin_access import AdminAccess
from models.agent import Agent
from models.schedule import Schedule
from models.usage import UsageMetric
from typing import Dict, List, Optional
from services.usage_service import normalize_plan


class AdminService:
    """
    Core admin functionality.
    All methods check if requester_id is actually an admin first.
    """

    @staticmethod
    def is_admin(db: Session, user_id: int) -> bool:
        """Check if user has admin access."""
        admin_record = db.query(AdminAccess).filter(AdminAccess.user_id == user_id).first()
        return admin_record is not None

    @staticmethod
    def grant_admin_access(db: Session, target_user_id: int, granted_by_user_id: int) -> bool:
        """
        Grant admin access to a user.
        Only an existing admin can do this.
        """
        if not AdminService.is_admin(db, granted_by_user_id):
            return False

        # Check if already admin
        existing = db.query(AdminAccess).filter(AdminAccess.user_id == target_user_id).first()
        if existing:
            return False

        admin_access = AdminAccess(
            user_id=target_user_id,
            role="admin",
            granted_by=granted_by_user_id,
        )
        db.add(admin_access)
        db.commit()
        return True

    @staticmethod
    def revoke_admin_access(db: Session, target_user_id: int, revoked_by_user_id: int) -> bool:
        """Revoke admin access from a user."""
        if not AdminService.is_admin(db, revoked_by_user_id):
            return False

        db.query(AdminAccess).filter(AdminAccess.user_id == target_user_id).delete()
        db.commit()
        return True

    @staticmethod
    def get_all_users(db: Session, skip: int = 0, limit: int = 50) -> List[Dict]:
        """Get all users with basic stats."""
        users = db.query(User).offset(skip).limit(limit).all()

        result = []
        for user in users:
            agent_count = db.query(func.count(Agent.id)).filter(Agent.user_id == user.id).scalar()
            schedule_count = db.query(func.count(Schedule.id)).filter(Schedule.user_id == user.id).scalar()

            result.append({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "plan": user.plan,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
                "agent_count": agent_count,
                "schedule_count": schedule_count,
                "paddle_customer_id": user.paddle_customer_id,
                "paddle_subscription_status": user.paddle_subscription_status,
            })

        return result

    @staticmethod
    def get_user_detail(db: Session, user_id: int) -> Optional[Dict]:
        """Get detailed stats for a single user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        agent_count = db.query(func.count(Agent.id)).filter(Agent.user_id == user.id).scalar()
        schedule_count = db.query(func.count(Schedule.id)).filter(Schedule.user_id == user.id).scalar()
        
        # Message usage this month
        from services.usage_service import UsageService
        month_start, month_end = UsageService.get_billing_month_range(user)
        messages_count = (
            db.query(func.count(UsageMetric.id))
            .filter(
                UsageMetric.user_id == user.id,
                UsageMetric.metric_type == "message",
                UsageMetric.created_at >= month_start,
                UsageMetric.created_at < month_end,
            )
            .scalar()
        )

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "plan": user.plan,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat(),
            "agent_count": agent_count,
            "schedule_count": schedule_count,
            "messages_this_month": messages_count,
            "paddle_customer_id": user.paddle_customer_id,
            "paddle_subscription_id": user.paddle_subscription_id,
            "paddle_subscription_status": user.paddle_subscription_status,
            "paddle_subscription_started_at": user.paddle_subscription_started_at.isoformat() if user.paddle_subscription_started_at else None,
            "paddle_subscription_next_billing_at": user.paddle_subscription_next_billing_at.isoformat() if user.paddle_subscription_next_billing_at else None,
        }

    @staticmethod
    def change_user_plan(db: Session, user_id: int, new_plan: str) -> bool:
        """
        Manually change a user's plan (admin override).
        Plans: "free", "starter", "pro", "business", "enterprise"
        """
        valid_plans = ["free", "starter", "pro", "business", "enterprise"]
        normalized_plan = normalize_plan(new_plan)
        if normalized_plan not in valid_plans:
            return False

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        user.plan = normalized_plan
        db.commit()
        return True

    @staticmethod
    def get_platform_stats(db: Session) -> Dict:
        """Get high-level platform statistics."""
        total_users = db.query(func.count(User.id)).scalar()
        active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
        
        # Users by plan
        free_users = db.query(func.count(User.id)).filter(User.plan == "free").scalar()
        starter_users = db.query(func.count(User.id)).filter(User.plan == "starter").scalar()
        pro_users = db.query(func.count(User.id)).filter(User.plan == "pro").scalar()
        business_users = db.query(func.count(User.id)).filter(User.plan == "business").scalar()
        enterprise_users = db.query(func.count(User.id)).filter(User.plan == "enterprise").scalar()

        # Agents and schedules
        total_agents = db.query(func.count(Agent.id)).scalar()
        total_schedules = db.query(func.count(Schedule.id)).scalar()

        # Messages (this month)
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        messages_this_month = (
            db.query(func.count(UsageMetric.id))
            .filter(
                UsageMetric.metric_type == "message",
                UsageMetric.created_at >= month_start,
            )
            .scalar()
        )

        # New users this week
        week_ago = now - timedelta(days=7)
        new_users_week = (
            db.query(func.count(User.id))
            .filter(User.created_at >= week_ago)
            .scalar()
        )

        return {
            "total_users": total_users,
            "active_users": active_users,
            "users_by_plan": {
                "free": free_users,
                "starter": starter_users,
                "pro": pro_users,
                "business": business_users,
                "enterprise": enterprise_users,
            },
            "total_agents": total_agents,
            "total_schedules": total_schedules,
            "messages_this_month": messages_this_month,
            "new_users_this_week": new_users_week,
        }

    @staticmethod
    def search_users(db: Session, query: str, limit: int = 20) -> List[Dict]:
        """Search users by name or email."""
        users = (
            db.query(User)
            .filter(
                User.name.ilike(f"%{query}%") | User.email.ilike(f"%{query}%")
            )
            .limit(limit)
            .all()
        )

        results = []
        for user in users:
            agent_count = db.query(func.count(Agent.id)).filter(Agent.user_id == user.id).scalar()
            schedule_count = db.query(func.count(Schedule.id)).filter(Schedule.user_id == user.id).scalar()

            results.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "plan": user.plan,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                    "agent_count": agent_count,
                    "schedule_count": schedule_count,
                    "paddle_customer_id": user.paddle_customer_id,
                    "paddle_subscription_status": user.paddle_subscription_status,
                }
            )

        return results

    @staticmethod
    def deactivate_user(db: Session, user_id: int) -> bool:
        """Deactivate a user (soft delete - they can't log in)."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        user.is_active = False
        db.commit()
        return True

    @staticmethod
    def reactivate_user(db: Session, user_id: int) -> bool:
        """Reactivate a deactivated user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        user.is_active = True
        db.commit()
        return True
