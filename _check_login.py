"""Diagnose login failures end-to-end. Run: python _check_login.py"""
import os, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///./research_platform.db")

errors = []

# ── 1. Check all auth models are imported by init_db ─────────────────────────
print("=== 1. Database tables ===")
try:
    from app.core.database import engine, Base, init_db
    init_db()
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"  Tables in DB: {sorted(tables)}")
    required = ["users", "refresh_tokens", "password_reset_tokens"]
    for t in required:
        if t in tables:
            print(f"  [OK] {t}")
        else:
            print(f"  [MISSING] {t}")
            errors.append(f"Table '{t}' missing from DB")
except Exception as e:
    errors.append(f"DB inspect failed: {e}")

# ── 2. Check security functions ───────────────────────────────────────────────
print("\n=== 2. Security functions ===")
try:
    from app.core.security import (
        hash_password, verify_password,
        create_access_token, decode_access_token,
        create_refresh_token, hash_token,
    )
    # Password round-trip
    h = hash_password("testpass123")
    assert verify_password("testpass123", h), "verify_password failed"
    assert not verify_password("wrongpass", h), "verify_password should reject wrong pass"
    print("  [OK] hash_password / verify_password")

    # JWT round-trip
    import uuid
    token = create_access_token(42, "test@test.com", jti=str(uuid.uuid4()))
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["email"] == "test@test.com"
    print("  [OK] create_access_token / decode_access_token")

    # Refresh token
    raw, hashed = create_refresh_token()
    assert hash_token(raw) == hashed
    print("  [OK] create_refresh_token / hash_token")

except Exception as e:
    import traceback
    traceback.print_exc()
    errors.append(f"Security: {e}")

# ── 3. Check SECRET_KEY is not the default placeholder ───────────────────────
print("\n=== 3. Config values ===")
from app.core.config import settings
if "changeme" in settings.secret_key:
    print("  [WARN] SECRET_KEY is still the default placeholder — JWT will work but is insecure")
else:
    print("  [OK] SECRET_KEY is set")

if "changeme" in settings.encryption_key:
    print("  [WARN] ENCRYPTION_KEY is still the default placeholder")
else:
    print("  [OK] ENCRYPTION_KEY is set")

# ── 4. Full register + login flow against real DB ────────────────────────────
print("\n=== 4. Register + Login flow ===")
try:
    from app.core.database import SessionLocal
    from app.services.auth_service import register, login
    from fastapi import HTTPException

    db = SessionLocal()
    TEST_EMAIL = "test_login_check@example.com"
    TEST_PASS  = "TestPass123!"

    # Clean up any previous test user
    from app.models.auth import User
    existing = db.query(User).filter_by(email=TEST_EMAIL).first()
    if existing:
        db.delete(existing)
        db.commit()

    # Register
    pair = register(TEST_EMAIL, TEST_PASS, "Test User", db)
    assert pair.access_token, "No access_token returned"
    assert pair.refresh_token, "No refresh_token returned"
    print("  [OK] register — tokens issued")

    # Login with correct password
    pair2 = login(TEST_EMAIL, TEST_PASS, db)
    assert pair2.access_token
    print("  [OK] login correct password — tokens issued")

    # Login with wrong password should raise 401
    try:
        login(TEST_EMAIL, "wrongpassword", db)
        errors.append("login with wrong password did NOT raise 401")
    except HTTPException as e:
        if e.status_code == 401:
            print("  [OK] login wrong password — 401 raised correctly")
        else:
            errors.append(f"login wrong password raised {e.status_code} not 401")

    # Decode the access token
    from app.core.security import decode_access_token
    payload = decode_access_token(pair2.access_token)
    assert payload["email"] == TEST_EMAIL
    print(f"  [OK] access_token decodes correctly (sub={payload['sub']})")

    # Clean up test user
    db.delete(db.query(User).filter_by(email=TEST_EMAIL).first())
    db.commit()
    db.close()

except Exception as e:
    import traceback
    traceback.print_exc()
    errors.append(f"Register/Login flow: {e}")

# ── 5. Check the /api/v1/auth/login route is registered ──────────────────────
print("\n=== 5. Route registration ===")
try:
    from main import app
    routes = {getattr(r, "path", ""): getattr(r, "methods", set()) for r in app.routes}
    login_path = "/api/v1/auth/login"
    if login_path in routes:
        print(f"  [OK] {login_path} registered — methods: {routes[login_path]}")
    else:
        errors.append(f"Route {login_path} NOT found in app")
        print(f"  [FAIL] {login_path} not registered")

    register_path = "/api/v1/auth/register"
    if register_path in routes:
        print(f"  [OK] {register_path} registered")
    else:
        errors.append(f"Route {register_path} NOT found")
except Exception as e:
    import traceback
    traceback.print_exc()
    errors.append(f"Route check: {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"RESULT: {len(errors)} problem(s) found:")
    for e in errors:
        print(f"  [FAIL] {e}")
    sys.exit(1)
else:
    print("RESULT: all login checks passed")
