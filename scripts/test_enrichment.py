import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.core.database import SessionLocal
from app.models.topic import Topic
from app.services.fulltext_enrichment import enrich_and_reingest

db = SessionLocal()
topic = db.query(Topic).first()
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
abstract_only = [p for p in included if p.parsed and len(p.chunks) <= 1]
print(f"Abstract-only: {len(abstract_only)} papers")
print("Testing enrichment on first 5...\n")

improved = 0
for paper in abstract_only[:5]:
    result = enrich_and_reingest(paper, db)
    got_better = result["downloaded"] or result["s2"] or result["arxiv"]
    if got_better:
        improved += 1
    status = "IMPROVED" if got_better else "no change"
    print(f"[{status}] [{paper.id}] {paper.title[:55]}")
    print(f"  arxiv={result['arxiv']} s2={result['s2']} unpaywall={result['unpaywall']}")
    print(f"  downloaded={result['downloaded']} chunks={result['chunks']}")
    print()

print(f"Improved: {improved}/5")
db.close()
