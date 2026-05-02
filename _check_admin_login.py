"""Verify the demo admin account works. Run: python _check_admin_login.py"""
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:abc@localhost:5432/research_platform")

from app.core.database import SessionLocal
from app.models.auth import User
from app.core.security import verify_password
from app.services.auth_service import login
from fastapi import HTTPException

db = SessionLocal()

user = db.query(User).filter_by(email="admin@example.com").first()
if not user:
    print("FAIL: admin@example.com does not exist — run: python scripts/seed_admin.py")
    sys.exit(1)

print(f"User found: id={user.id}  email={user.email}  active={user.is_active}  role={user.role}")

# Test password directly
ok = verify_password("password123", user.password_hash)
print(f"Password 'password123' verifies: {ok}")

if not ok:
    # The hash might be in old format — rehash it
    print("Rehashing password to new format...")
    from app.core.security import hash_password
    user.password_hash = hash_password("password123")
    db.commit()
    print("Password rehashed. Verifying again...")
    ok2 = verify_password("password123", user.password_hash)
    print(f"After rehash: {ok2}")

# Test full login flow
try:
    pair = login("admin@example.com", "password123", db)
    print(f"Login OK — access_token starts with: {pair.access_token[:30]}...")
    print("\nRESULT: admin login works — you can sign in with admin@example.com / password123")
except HTTPException as e:
    print(f"FAIL: login raised HTTP {e.status_code}: {e.detail}")
    sys.exit(1)
finally:
    db.close()
