"""JWT + bcrypt security utilities."""
import hashlib
import secrets
from datetime import datetime, timezone

import bcrypt
from fastapi import HTTPException, status
from jose import JWTError, jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_utcnow = lambda: datetime.now(timezone.utc)  # noqa: E731


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password with bcrypt cost=12.

    bcrypt silently truncates at 72 bytes; we pre-hash with SHA-256 to support
    arbitrarily long passwords while keeping the full entropy.
    """
    # SHA-256 digest is always 32 bytes — safely within bcrypt's 72-byte limit
    digest = hashlib.sha256(password.encode()).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against stored hash.

    Supports both old format (bcrypt(password)) and new format (bcrypt(sha256(password))).
    This ensures backward compatibility for users registered before the sha256 pre-hash fix.
    """
    try:
        hashed_bytes = hashed.encode()
        # Try new format first: bcrypt(sha256(password))
        digest = hashlib.sha256(plain.encode()).digest()
        if bcrypt.checkpw(digest, hashed_bytes):
            return True
        # Fallback: try old format bcrypt(password) for existing users
        try:
            return bcrypt.checkpw(plain.encode()[:72], hashed_bytes)
        except Exception:
            return False
    except ValueError:
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str, jti: str) -> str:
    """Create JWT access token with 24h expiry (exp - iat == 86400s)."""
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + 86400,
        "jti": jti,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and validate JWT. Raises HTTP 401 if invalid or expired."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid or expired",
        )


# ── Refresh token ─────────────────────────────────────────────────────────────

def create_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Store only the hash."""
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ── GitHub token encryption ──────────────────────────────────────────────────

def _derive_aes_key() -> bytes:
    """Derive a stable 32-byte key from the configured encryption secret."""
    return hashlib.sha256(settings.encryption_key.encode()).digest()


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage using AES-GCM. Returns nonce+ciphertext as hex."""
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(_derive_aes_key())
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return f"aesgcm:{(nonce + ciphertext).hex()}"


def decrypt_secret(stored_value: str) -> str:
    """Decrypt a secret stored by encrypt_secret. Falls back to legacy base64 values."""
    if not stored_value:
        return ""
    if stored_value.startswith("aesgcm:"):
        raw = bytes.fromhex(stored_value.removeprefix("aesgcm:"))
        nonce, ciphertext = raw[:12], raw[12:]
        aesgcm = AESGCM(_derive_aes_key())
        return aesgcm.decrypt(nonce, ciphertext, None).decode()

    # Legacy fallback: old base64-encoded token
    import base64

    try:
        return base64.b64decode(stored_value.encode()).decode()
    except Exception:
        return stored_value
