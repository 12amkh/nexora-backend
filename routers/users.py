# routers/users.py

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from database import get_db
from models.user import User
from models.agent import Agent
from models.conversation import Conversation
from services.admin_service import AdminService
from schemas.user import UserResponse, UserThemeUpdate
from utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


def serialize_user_response(user: User, db: Session) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        plan=user.plan,
        is_admin=AdminService.is_admin(db, user.id),
        theme=user.theme,
        theme_family=user.theme_family,
        created_at=user.created_at,
    )


# ── Update Schema ─────────────────────────────────────────────────────────────────
# defined here because it's small and only used by this router
# validates input before it ever touches the database
class UserUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty.")
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters.")
        if len(v) > 100:
            raise ValueError("Name cannot exceed 100 characters.")
        return v


# ── Get Current User ──────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the current authenticated user's profile",
)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logger.info(f"Profile fetched for user {current_user.id} ({current_user.email})")
    return serialize_user_response(current_user, db)


# ── Update Profile ────────────────────────────────────────────────────────────────
@router.put(
    "/update",
    response_model=UserResponse,
    summary="Update the current user's profile",
)
def update_profile(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    old_name = current_user.name
    current_user.name = update_data.name

    db.commit()
    db.refresh(current_user)

    logger.info(
        f"Profile updated for user {current_user.id}: "
        f"name '{old_name}' → '{current_user.name}'"
    )
    return serialize_user_response(current_user, db)


@router.put(
    "/theme",
    response_model=UserResponse,
    summary="Update the current user's theme preference",
)
def update_theme(
    update_data: UserThemeUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.theme = update_data.theme
    current_user.theme_family = update_data.theme_family
    db.commit()
    db.refresh(current_user)

    logger.info(
        f"Theme updated for user {current_user.id}: mode='{current_user.theme}' family='{current_user.theme_family}'"
    )
    return serialize_user_response(current_user, db)


# ── Get User Stats ────────────────────────────────────────────────────────────────
# useful for the frontend dashboard — shows usage at a glance
# real life: your Spotify wrapped — how much have you used the product?
@router.get(
    "/stats",
    summary="Get usage statistics for the current user",
)
def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total_agents = db.query(Agent).filter(
        Agent.user_id == current_user.id
    ).count()

    total_messages = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).count()

    # count only user-sent messages (not assistant responses)
    user_messages = db.query(Conversation).filter(
        Conversation.user_id == current_user.id,
        Conversation.role == "user",
    ).count()

    logger.info(f"Stats fetched for user {current_user.id}")

    return {
        "user_id":        current_user.id,
        "name":           current_user.name,
        "email":          current_user.email,
        "plan":           current_user.plan,
        "total_agents":   total_agents,
        "total_messages": total_messages,
        "messages_sent":  user_messages,
    }


# ── Delete Account ────────────────────────────────────────────────────────────────
# GDPR compliance — users must be able to delete their own data
# deletes everything: conversations → agents → user (order matters for FK constraints)
@router.delete(
    "/delete",
    status_code=status.HTTP_200_OK,
    summary="Permanently delete the current user's account and all data",
)
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id
    email = current_user.email

    # delete in correct order to respect foreign key constraints
    # conversations → agents → user
    deleted_conversations = db.query(Conversation).filter(
        Conversation.user_id == user_id
    ).delete()

    deleted_agents = db.query(Agent).filter(
        Agent.user_id == user_id
    ).delete()

    db.delete(current_user)
    db.commit()

    logger.info(
        f"Account deleted: user {user_id} ({email}) — "
        f"{deleted_agents} agents, {deleted_conversations} conversations removed"
    )

    return {
        "message": "Your account and all associated data have been permanently deleted."
    }
