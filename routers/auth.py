# routers/auth.py

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from schemas.user import UserRegister, UserResponse
from schemas.token import Token
from utils.hashing import hash_password, verify_password
from utils.auth import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# ── Brute Force Protection ────────────────────────────────────────────────────────
# simple in-memory rate limiter — tracks failed login attempts per IP
# real life: a bank locks your account after 5 wrong PIN attempts
# in production with multiple server instances, use Redis instead (Stage: Cache)
# structure: { "ip_address": {"count": int, "locked_until": timestamp} }
_failed_attempts: dict = {}
MAX_ATTEMPTS = 5       # max failed logins before lockout
LOCKOUT_SECONDS = 300  # 5 minute lockout after too many failures

import time

def check_rate_limit(ip: str):
    """Block IP if too many failed login attempts."""
    now = time.time()
    record = _failed_attempts.get(ip)

    if record:
        # check if still locked out
        if record["locked_until"] and now < record["locked_until"]:
            remaining = int(record["locked_until"] - now)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Try again in {remaining} seconds."
            )
        # reset if lockout has expired
        if record["locked_until"] and now >= record["locked_until"]:
            _failed_attempts[ip] = {"count": 0, "locked_until": None}


def record_failed_attempt(ip: str):
    """Increment failed attempt counter and lock if threshold reached."""
    now = time.time()
    if ip not in _failed_attempts:
        _failed_attempts[ip] = {"count": 0, "locked_until": None}

    _failed_attempts[ip]["count"] += 1

    if _failed_attempts[ip]["count"] >= MAX_ATTEMPTS:
        _failed_attempts[ip]["locked_until"] = now + LOCKOUT_SECONDS
        logger.warning(f"IP {ip} locked out after {MAX_ATTEMPTS} failed login attempts")


def clear_failed_attempts(ip: str):
    """Clear failed attempts after successful login."""
    if ip in _failed_attempts:
        del _failed_attempts[ip]


# ── Password Validation ───────────────────────────────────────────────────────────
def validate_password_strength(password: str):
    """
    Enforce password rules before storing anything.
    Real life: TSA rules at the airport — checked before you board, not after.
    """
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )
    if not any(c.isupper() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter."
        )
    if not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one number."
        )


# ── Register ──────────────────────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,  # 201 = resource created (more correct than 200)
    summary="Register a new user account",
)
def register(user: UserRegister, db: Session = Depends(get_db)):
    # normalize email — prevent "User@Email.COM" and "user@email.com" as duplicates
    normalized_email = user.email.strip().lower()

    # enforce password strength before touching the DB
    validate_password_strength(user.password)

    # check for duplicate email
    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists."
        )

    # create user
    new_user = User(
        name=user.name.strip(),
        email=normalized_email,
        password_hash=hash_password(user.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info(f"New user registered: {normalized_email} (id={new_user.id})")
    return new_user


# ── Login ─────────────────────────────────────────────────────────────────────────
@router.post(
    "/login",
    response_model=Token,
    summary="Login and receive a JWT access token",
)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # get client IP for rate limiting
    # request.client.host gives the raw IP address
    ip = request.client.host if request.client else "unknown"

    # block if IP has too many recent failures
    check_rate_limit(ip)

    # normalize email
    email = form_data.username.strip().lower()

    # look up user
    db_user = db.query(User).filter(User.email == email).first()

    # IMPORTANT: always check both user existence AND password before failing
    # never reveal whether the email exists or the password was wrong separately
    # real life: a good bouncer says "you're not on the list" not "wrong password"
    if not db_user or not verify_password(form_data.password, db_user.password_hash):
        record_failed_attempt(ip)
        logger.warning(f"Failed login attempt for email: {email} from IP: {ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # successful login — clear failed attempts and issue token
    clear_failed_attempts(ip)

    token = create_access_token(data={
        "user_id": db_user.id,
        "email": db_user.email,
    })

    logger.info(f"User logged in: {email} (id={db_user.id}) from IP: {ip}")

    return {
        "access_token": token,
        "token_type": "bearer",
    }