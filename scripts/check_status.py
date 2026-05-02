"""Check current pipeline status and diagnose screen stage."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

from app.core.database import SessionLocal
from app.models.pipeline import PipelineRun
from app.models.paper import Paper, PaperDecision
from app.models.topic import Topic

db = SessionLocal()

# All topics
topics = db.query(Topic).all()
print(f"Topics: {len(topics)}")
for t in topics:
    print(f"  [{t.id}] {t.title}")

print()

# Latest pipeline runs
runs = db.query(PipelineRun).order_by(PipelineRun.id.desc()).limit(20).all()
print(f"Recent pipeline runs (latest 20):")
for r in runs:
    dur = ""
    if r.started_at and r.finished_at:
        dur = f" ({(r.finished_at - r.started_at).seconds}s)"
    elif r.started_at:
        from datetime import datetime, timezone
        dur = f" (running {(datetime.now() - r.started_at).seconds}s so far)"
    print(f"  [{r.id}] topic={r.topic_id} stage={r.stage:<12} status={r.status:<8}{dur}")
    if r.error:
        print(f"         ERROR: {r.error[:120]}")
    if r.result_summary:
        print(f"         result: {r.result_summary}")

print()

# Paper stats per topic
for t in topics:
    papers = db.query(Paper).filter_by(topic_id=t.id).all()
    decisions = db.query(PaperDecision).join(Paper).filter(Paper.topic_id == t.id).all()
    label_counts = {}
    for d in decisions:
        label_counts[d.label] = label_counts.get(d.label, 0) + 1
    print(f"Topic [{t.id}] papers={len(papers)} screened={len(decisions)} labels={label_counts}")

db.close()
