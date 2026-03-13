# utils/dependencies.py

import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from utils.auth import verify_token

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    # single reusable exception — never reveal WHY auth failed
    # real life: a bouncer says "you're not coming in"
    # not "your ID is expired" — that's too much information
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # decode and verify the JWT token
        payload = verify_token(token)

        if payload is None:
            logger.warning("Token verification returned None")
            raise credentials_exception

        # extract user_id from token payload
        user_id: int = payload.get("user_id")

        if user_id is None:
            logger.warning("Token payload missing user_id field")
            raise credentials_exception

        # fetch user from DB — verify they still exist
        # important: user could be deleted after token was issued
        user = db.query(User).filter(User.id == user_id).first()

        if user is None:
            logger.warning(f"Token valid but user {user_id} not found in DB — possibly deleted")
            raise credentials_exception

        return user

    except HTTPException:
        # re-raise HTTP exceptions as-is — don't wrap them
        raise

    except Exception as e:
        # log unexpected errors with full detail server-side
        # but return the same generic 401 to the client
        logger.error(f"Unexpected error in get_current_user: {e}", exc_info=True)
        raise credentials_exception