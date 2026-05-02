"""Test Unpaywall on papers with DOI but no arXiv ID."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

from app.core.database import SessionLocal
from app.models.topic import Topic
from app.services.fulltext_enrichment import _s2_batch_enrich, _unpaywall_get_pdf

db = SessionLocal()
topic = db.query(Topic).first()
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
abstract_only = [p for p in included if p.parsed and len(p.chunks) <= 1]

# Get S2 data to find DOIs
s2_data = _s2_batch_enrich(abstract_only[:20], db)

# Filter: has DOI, no arXiv
doi_only = [(p, s2_data[p.id]) for p in abstract_only[:20]
            if p.id in s2_data and s2_data[p.id].get("doi") and not s2_data[p.id].get("arxiv_id")]

print(f"Papers with DOI but no arXiv: {len(doi_only)}")
print("Testing Unpaywall on first 5...\n")

found = 0
for paper, data in doi_only[:5]:
    doi = data["doi"]
    pdf = _unpaywall_get_pdf(doi)
    status = "PDF FOUND" if pdf else "no OA"
    if pdf: found += 1
    print(f"[{status}] [{paper.id}] {paper.title[:50]}")
    print(f"  doi={doi}")
    print(f"  pdf={pdf[:70] if pdf else 'none'}")
    time.sleep(0.3)

print(f"\nResult: {found}/{min(5,len(doi_only))} PDF found via Unpaywall")
db.close()
