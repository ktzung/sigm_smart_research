import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.core.database import SessionLocal
from app.models.topic import Topic

db = SessionLocal()
topic = db.query(Topic).first()
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
abstract_only = [p for p in included if p.parsed and len(p.chunks) <= 1]

print("Sample abstract-only papers - checking IDs and URLs:")
for p in abstract_only[:8]:
    print(f"  [{p.id}] source={p.source_api} external_id={p.external_id} url={p.url[:60] if p.url else 'none'}")
db.close()
