"""Test ingest speed on papers with pdf_url."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

from app.core.database import SessionLocal
from app.models.topic import Topic
from app.services.ingestion import ingest_paper, _is_skippable_url

db = SessionLocal()
topic = db.query(Topic).first()
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
unparsed = [p for p in included if not p.parsed]

print(f"Unparsed papers: {len(unparsed)}")
print(f"With pdf_url   : {sum(1 for p in unparsed if p.pdf_url)}")
print(f"Skippable URLs : {sum(1 for p in unparsed if p.pdf_url and _is_skippable_url(p.pdf_url))}")
print(f"No pdf_url     : {sum(1 for p in unparsed if not p.pdf_url)}")
print()

# Time ingest on first 5 unparsed papers
print("Timing ingest on first 5 unparsed papers:")
t_total = time.time()
for paper in unparsed[:5]:
    t0 = time.time()
    result = ingest_paper(paper, db)
    elapsed = time.time() - t0
    print(f"  [{paper.id}] {paper.title[:50]:<50} -> {result}  ({elapsed:.1f}s)")

print(f"\nTotal: {time.time()-t_total:.1f}s for 5 papers")
print(f"Estimated for {len(unparsed)} papers: {(time.time()-t_total)/5*len(unparsed):.0f}s")
db.close()
