import sys
import os
sys.path.insert(0, os.getcwd())

from app.core.database import SessionLocal, init_db
from app.models.auth import User
from app.models.news import News
from app.services.auth_service import register

def seed_data():
    init_db()
    db = SessionLocal()
    try:
        # 1. Create Admins
        admin = db.query(User).filter_by(email='admin@example.com').first()
        if not admin:
            admin = register("admin@example.com", "password123", "System Admin", db)
        admin.role = "admin"
        db.commit()
        print(f"Admin created: {admin.email}")

        # 2. Create Regular Users
        users = [
            ("prof.nguyen@hust.edu.vn", "password123", "Prof. Nguyen Van A"),
            ("dr.tran@hust.edu.vn", "password123", "Dr. Tran Thi B"),
            ("student.le@hust.edu.vn", "password123", "Le Van C"),
        ]
        user_objs = []
        for email, pwd, name in users:
            u = db.query(User).filter_by(email=email).first()
            if not u:
                u = register(email, pwd, name, db)
                print(f"User created: {email}")
            user_objs.append(u)

        # 3. Create News
        news_items = [
            ("Welcome to SigMSmartResearch", "We are excited to launch our new Research Automation Platform for HUST researchers.", True),
            ("New Paper Type: Systematic Review", "The platform now supports full 16-stage systematic review pipelines.", True),
            ("Maintenance Notice", "Server maintenance scheduled for Sunday midnight.", False),
            ("HUST AI Lab wins Q1 Paper award", "Congratulations to our members for the recent publication in IEEE TPAMI.", True),
        ]
        for title, content, public in news_items:
            n = db.query(News).filter_by(title=title).first()
            if not n:
                n = News(title=title, content=content, is_public=public, author_id=admin.id)
                db.add(n)
                print(f"News created: {title}")
        
        db.commit()
        print("Seeding complete.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
