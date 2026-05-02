import sys
import os
sys.path.insert(0, os.getcwd())

from app.core.database import SessionLocal, init_db
from app.models.auth import User
from app.services.auth_service import register

def check_or_create_admin():
    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email='admin@example.com').first()
        if user:
            print("User admin@example.com already exists.")
        else:
            print("Creating admin@example.com...")
            register("admin@example.com", "password123", "Admin User", db)
            print("User admin@example.com created with password: password123")
    finally:
        db.close()

if __name__ == "__main__":
    check_or_create_admin()
