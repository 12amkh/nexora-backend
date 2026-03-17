import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from database import get_db
from models.notification import Notification
from models.user import User
from schemas.notification import (
    MarkAllNotificationsReadResponse,
    NotificationListResponse,
    NotificationResponse,
)
from utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


@router.get(
    "/list",
    response_model=NotificationListResponse,
    summary="List recent notifications for the current user",
)
def list_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=30, description="Max notifications to return"),
):
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )
    unread_count = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .scalar()
        or 0
    )

    logger.info(
        "Notifications fetched: user=%s unread=%s returned=%s",
        current_user.id,
        unread_count,
        len(notifications),
    )
    return NotificationListResponse(notifications=notifications, unread_count=unread_count)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark a notification as read",
)
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found.",
        )

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = func.now()
        db.commit()
        db.refresh(notification)

    logger.info("Notification read: id=%s user=%s", notification_id, current_user.id)
    return notification


@router.post(
    "/read-all",
    response_model=MarkAllNotificationsReadResponse,
    summary="Mark all notifications as read",
)
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .all()
    )

    for notification in notifications:
        notification.is_read = True
        notification.read_at = func.now()

    db.commit()

    updated_count = len(notifications)
    logger.info("Notifications marked read: user=%s updated=%s", current_user.id, updated_count)
    return MarkAllNotificationsReadResponse(updated_count=updated_count)
