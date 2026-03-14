from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from utils.dependencies import get_current_user
from services.admin_service import AdminService

router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)


def require_admin(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Dependency to ensure user is admin."""
    if not AdminService.is_admin(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# ── Platform Overview ─────────────────────────────────────────────────────────────
@router.get(
    "/stats",
    summary="Get high-level platform statistics (admins only)"
)
async def get_platform_stats(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get overview stats:
    - Total users by plan
    - Total agents created
    - Total schedules
    - Messages sent this month
    - New users this week
    """
    stats = AdminService.get_platform_stats(db)
    return {"success": True, "data": stats}


# ── Users List ────────────────────────────────────────────────────────────────────
@router.get(
    "/users",
    summary="Get paginated list of all users"
)
async def get_all_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
):
    """Get all users with basic stats (paginated)."""
    users = AdminService.get_all_users(db, skip=skip, limit=limit)
    return {"success": True, "data": users, "count": len(users)}


# ── User Detail ───────────────────────────────────────────────────────────────────
@router.get(
    "/users/{user_id}",
    summary="Get detailed stats for a single user"
)
async def get_user_detail(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get detailed user info including usage, Paddle subscription status, etc."""
    user = AdminService.get_user_detail(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"success": True, "data": user}


# ── Search Users ──────────────────────────────────────────────────────────────────
@router.get(
    "/users/search",
    summary="Search users by name or email"
)
async def search_users(
    q: str = Query(..., min_length=1, max_length=100),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Search users by name or email."""
    results = AdminService.search_users(db, q)
    return {"success": True, "data": results, "count": len(results)}


# ── Change User Plan ──────────────────────────────────────────────────────────────
@router.post(
    "/users/{user_id}/change-plan",
    summary="Manually change a user's plan (admin override)"
)
async def change_user_plan(
    user_id: int,
    plan: str = Query(..., regex="^(free|starter|pro|business|enterprise)$"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin can manually change a user's plan.
    Useful for:
    - Offering free trials
    - Handling payment issues
    - Testing different tiers
    """
    success = AdminService.change_user_plan(db, user_id, plan)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to change plan")
    return {"success": True, "message": f"User {user_id} plan changed to {plan}"}


# ── Deactivate User ──────────────────────────────────────────────────────────────
@router.post(
    "/users/{user_id}/deactivate",
    summary="Deactivate a user (soft delete)"
)
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Deactivate a user (they can't log in).
    Does NOT delete their data - just marks as inactive.
    """
    success = AdminService.deactivate_user(db, user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"success": True, "message": f"User {user_id} deactivated"}


# ── Reactivate User ──────────────────────────────────────────────────────────────
@router.post(
    "/users/{user_id}/reactivate",
    summary="Reactivate a deactivated user"
)
async def reactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reactivate a user so they can log in again."""
    success = AdminService.reactivate_user(db, user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"success": True, "message": f"User {user_id} reactivated"}


# ── Grant Admin Access ────────────────────────────────────────────────────────────
@router.post(
    "/grant-admin/{target_user_id}",
    summary="Grant admin access to a user"
)
async def grant_admin_access(
    target_user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Grant admin access to another user.
    Only existing admins can grant admin access.
    """
    success = AdminService.grant_admin_access(db, target_user_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to grant admin access (user may already be admin)"
        )
    return {"success": True, "message": f"Admin access granted to user {target_user_id}"}


# ── Revoke Admin Access ───────────────────────────────────────────────────────────
@router.post(
    "/revoke-admin/{target_user_id}",
    summary="Revoke admin access from a user"
)
async def revoke_admin_access(
    target_user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Revoke admin access from a user."""
    success = AdminService.revoke_admin_access(db, target_user_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to revoke admin access")
    return {"success": True, "message": f"Admin access revoked from user {target_user_id}"}