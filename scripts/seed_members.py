import sys
import os
sys.path.insert(0, os.getcwd())

from app.core.database import SessionLocal, init_db
from app.models.auth import User
from app.models.lab import Lab, LabMember
from app.services.auth_service import register

def seed_members():
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(role='admin').first()
        if not admin:
            register("admin@example.com", "password123", "System Admin", db)
            admin = db.query(User).filter_by(role='admin').first()

        lab = db.query(Lab).filter_by(name="SigM AI Lab").first()
        if not lab:
            lab = Lab(name="SigM AI Lab", description="HUST Advanced AI & Research Automation Laboratory", owner_id=admin.id)
            db.add(lab)
            db.commit()
            db.refresh(lab)

        members_data = [
            ("prof.nguyen@hust.edu.vn", "password123", "Prof. Nguyen Van A", "professor"),
            ("dr.tran@hust.edu.vn", "password123", "Dr. Tran Thi B", "professor"),
            ("phd.hoang@hust.edu.vn", "password123", "Hoang Van D", "phd_student"),
            ("phd.minh@hust.edu.vn", "password123", "Nguyen Quang Minh", "phd_student"),
            ("master.an@hust.edu.vn", "password123", "Le Thanh An", "master_student"),
            ("student.le@hust.edu.vn", "password123", "Pham Van C", "undergraduate_student"),
        ]

        for email, pwd, name, role in members_data:
            u = db.query(User).filter_by(email=email.lower()).first()
            if not u:
                register(email, pwd, name, db)
                u = db.query(User).filter_by(email=email.lower()).first()
            
            membership = db.query(LabMember).filter_by(lab_id=lab.id, user_id=u.id).first()
            if not membership:
                membership = LabMember(lab_id=lab.id, user_id=u.id, role=role)
                db.add(membership)
                print(f"Added member: {name} as {role}")
        
        db.commit()
        print("Member seeding complete.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_members()
