from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from utils.dependencies import get_current_user
from database import get_db
from services.usage_service import UsageService
from models.user import User

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/stats")
async def get_usage_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current usage + limits for the logged-in user.
    Shown on dashboard to display "X/Y messages used this month".
    """
    stats = UsageService.get_usage_stats(db, current_user.id)
    return {"success": True, "data": stats}