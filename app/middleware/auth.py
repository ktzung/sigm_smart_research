"""JWT auth dependency — inject into any route that requires authentication."""
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.auth import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# Paths that don't require auth (checked by prefix)
AUTH_WHITELIST = {
    "/health",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/reset-password/request",
    "/api/v1/auth/reset-password/confirm",
}

# Path prefixes that are public (profile/homepage reads)
PUBLIC_PREFIXES = (
    "/api/v1/users/",       # GET /users/{user_id}/profile, publications, projects
    "/api/v1/labs/",        # GET /labs/{lab_id}/homepage, news, events
    "/storage/",
    "/static/",
    "/docs",
    "/openapi",
)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode JWT and return the authenticated User. Raises 401 if invalid."""
    if not token:
        raise HTTPException(401, detail="Token invalid or expired")
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401, detail="Token invalid or expired")

    user = db.query(User).filter_by(id=user_id, is_active=True).first()
    if not user:
        raise HTTPException(401, detail="Token invalid or expired")
    return user


def get_optional_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of raising for public endpoints."""
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        return db.query(User).filter_by(id=user_id, is_active=True).first()
    except (JWTError, KeyError, ValueError):
        return None
    except Exception:
        import logging
        logging.getLogger(__name__).debug("Unexpected error in get_optional_user", exc_info=True)
        return None
