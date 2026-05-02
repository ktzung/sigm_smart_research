from app.core.database import SessionLocal
from app.models.auth import User
from app.models.lab import Lab, LabMember

db = SessionLocal()

print("=== USERS ===")
users = db.query(User).all()
for u in users:
    role = getattr(u, 'role', 'N/A')
    print(f"  id={u.id} email={u.email} plan={u.plan} role={role} active={u.is_active}")

print()
print("=== LABS ===")
labs = db.query(Lab).all()
for l in labs:
    print(f"  id={l.id} name={l.name} owner_id={l.owner_id}")

print()
print("=== LAB MEMBERS ===")
members = db.query(LabMember).all()
for m in members:
    print(f"  lab_id={m.lab_id} user_id={m.user_id} role={m.role}")

db.close()
