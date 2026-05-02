"""Fix pipeline runs stuck in 'running' state after server restart."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.models.pipeline import PipelineRun

db = SessionLocal()
_utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)

stuck = db.query(PipelineRun).filter_by(status="running").all()
print(f"Found {len(stuck)} stuck run(s):")
for r in stuck:
    age = (datetime.now() - r.started_at).seconds if r.started_at else 0
    print(f"  [{r.id}] stage={r.stage} started={r.started_at} age={age}s")
    r.status = "failed"
    r.error = "Interrupted: server was restarted while stage was running"
    r.finished_at = _utcnow()

db.commit()
print("Fixed. All stuck runs marked as failed.")
db.close()
