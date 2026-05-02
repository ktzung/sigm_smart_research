"""Authentication service: register, login, refresh, logout, password reset."""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, hash_token,
)
from app.core.config import settings
from app.models.auth import User, RefreshToken, PasswordResetToken

logger = logging.getLogger(__name__)
_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthService:
    """Handles registration, login, token management, and password reset."""

    # ── Register ──────────────────────────────────────────────────────────────

    def register(self, email: str, password: str, display_name: str, db: Session) -> TokenPair:
        """Validate input, hash password, create User, return TokenPair.
        Raises HTTP 422 for invalid input, HTTP 400 if email already exists.
        """
        if len(password) < 8:
            raise HTTPException(422, detail="Password must be at least 8 characters")
        if not email or "@" not in email:
            raise HTTPException(422, detail="Invalid email address")
        if not display_name.strip():
            raise HTTPException(422, detail="Display name must not be empty")

        existing = db.query(User).filter_by(email=email.lower()).first()
        if existing:
            raise HTTPException(400, detail="Email already registered")

        user = User(
            email=email.lower(),
            display_name=display_name.strip(),
            password_hash=hash_password(password),
            plan="free",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("User registered: %s (id=%d)", user.email, user.id)
        return self._issue_token_pair(user, db)

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(self, email: str, password: str, db: Session) -> TokenPair:
        """Lookup user by email, verify password, return TokenPair.
        Raises HTTP 401 with detail="Invalid credentials" for any failure.
        """
        user = db.query(User).filter_by(email=email.lower()).first()
        # Constant-time: always verify even if user not found (prevents timing attacks)
        dummy_hash = "$2b$12$dummy.hash.to.prevent.timing.attacks.xxxxxxxxxxxxxxxxxx"
        stored_hash = user.password_hash if user else dummy_hash
        valid = verify_password(password, stored_hash)

        if not user or not valid or not user.is_active:
            raise HTTPException(401, detail="Invalid credentials")

        logger.info("User logged in: %s", user.email)
        return self._issue_token_pair(user, db)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self, refresh_token: str, db: Session) -> TokenPair:
        """Hash raw token, find RefreshToken, check not revoked/expired,
        create new token pair, revoke old token.
        """
        token_hash = hash_token(refresh_token)
        record = db.query(RefreshToken).filter_by(token_hash=token_hash).first()

        if not record or record.revoked or record.expires_at < _utcnow():
            raise HTTPException(401, detail="Token invalid or expired")

        user = db.query(User).filter_by(id=record.user_id).first()
        if not user or not user.is_active:
            raise HTTPException(401, detail="Token invalid or expired")

        # Revoke old token (rotation)
        record.revoked = True
        db.commit()

        return self._issue_token_pair(user, db)

    # ── Logout ────────────────────────────────────────────────────────────────

    def logout(self, user_id: int, refresh_token: str, db: Session) -> None:
        """Hash token, find and revoke it."""
        token_hash = hash_token(refresh_token)
        record = db.query(RefreshToken).filter_by(token_hash=token_hash, user_id=user_id).first()
        if record:
            record.revoked = True
            db.commit()

    # ── Password reset ────────────────────────────────────────────────────────

    def request_password_reset(self, email: str, db: Session) -> None:
        """Create PasswordResetToken (1h expiry), log the reset link.
        Does not fail if SMTP not configured. Silent if email not found.
        """
        user = db.query(User).filter_by(email=email.lower()).first()
        if not user:
            return  # Silent — don't reveal if email exists

        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        expires_at = _utcnow() + timedelta(hours=1)

        reset = PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
        db.add(reset)
        db.commit()

        reset_url = f"http://localhost:8000/reset-password?token={raw_token}"
        _send_reset_email(user.email, reset_url)

    def reset_password(self, token: str, new_password: str, db: Session) -> None:
        """Hash token, find PasswordResetToken, validate not used/expired,
        hash new password, update user, mark token used.
        """
        if len(new_password) < 8:
            raise HTTPException(422, detail="Password must be at least 8 characters")

        token_hash = hash_token(token)
        record = db.query(PasswordResetToken).filter_by(token_hash=token_hash).first()

        if not record or record.used or record.expires_at < _utcnow():
            raise HTTPException(400, detail="Reset token invalid or expired")

        user = db.query(User).filter_by(id=record.user_id).first()
        if not user:
            raise HTTPException(400, detail="Reset token invalid or expired")

        user.password_hash = hash_password(new_password)
        record.used = True
        # Revoke all refresh tokens for security
        db.query(RefreshToken).filter_by(user_id=user.id).update({"revoked": True})
        db.commit()
        logger.info("Password reset for user %d", user.id)

    # ── Invalidate all tokens ─────────────────────────────────────────────────

    def invalidate_all_tokens(self, user_id: int, db: Session) -> None:
        """Set revoked=True for all RefreshTokens of user."""
        db.query(RefreshToken).filter_by(user_id=user_id).update({"revoked": True})
        db.commit()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _issue_token_pair(self, user: User, db: Session) -> TokenPair:
        access = create_access_token(user.id, user.email, jti=str(uuid.uuid4()))
        raw_refresh, refresh_hash = create_refresh_token()
        expires_at = _utcnow() + timedelta(days=settings.refresh_token_expire_days)

        rt = RefreshToken(user_id=user.id, token_hash=refresh_hash, expires_at=expires_at)
        db.add(rt)
        db.commit()

        return TokenPair(access_token=access, refresh_token=raw_refresh)


# ── Module-level singleton + backward-compatible function aliases ─────────────

auth_service = AuthService()

# Keep module-level functions so existing callers (api/auth.py, scripts) work unchanged
def register(email: str, password: str, display_name: str, db: Session) -> TokenPair:
    return auth_service.register(email, password, display_name, db)

def login(email: str, password: str, db: Session) -> TokenPair:
    return auth_service.login(email, password, db)

def refresh(raw_refresh_token: str, db: Session) -> TokenPair:
    return auth_service.refresh(raw_refresh_token, db)

def logout(user_id: int, raw_refresh_token: str, db: Session) -> None:
    return auth_service.logout(user_id, raw_refresh_token, db)

def request_password_reset(email: str, db: Session) -> None:
    return auth_service.request_password_reset(email, db)

def reset_password(raw_token: str, new_password: str, db: Session) -> None:
    return auth_service.reset_password(raw_token, new_password, db)

def invalidate_all_tokens(user_id: int, db: Session) -> None:
    return auth_service.invalidate_all_tokens(user_id, db)


def _send_reset_email(email: str, reset_url: str) -> None:
    if not settings.smtp_host:
        logger.info("SMTP not configured. Password reset URL for %s: %s", email, reset_url)
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(f"Reset your password: {reset_url}\n\nExpires in 1 hour.")
        msg["Subject"] = "ChimCanhCut — Password Reset"
        msg["From"] = settings.smtp_from
        msg["To"] = email
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
            if settings.smtp_user:
                s.starttls()
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except Exception as e:
        logger.error("Failed to send reset email to %s: %s", email, e)
