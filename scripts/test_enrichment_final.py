"""Test final enrichment flow on 10 abstract-only papers."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

from app.core.database import SessionLocal
from app.models.topic import Topic
from app.services.fulltext_enrichment import _s2_batch_enrich, enrich_paper

db = SessionLocal()
topic = db.query(Topic).first()
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
abstract_only = [p for p in included if p.parsed and len(p.chunks) <= 1]
sample = abstract_only[:10]

print(f"Testing enrichment on {len(sample)} papers...\n")

# S2 batch
s2_data = _s2_batch_enrich(sample, db)
print(f"S2 batch returned: {len(s2_data)}/{len(sample)} papers\n")

improved, pdf_dl = 0, 0
for paper in sample:
    data = s2_data.get(paper.id, {})
    chunks_before = len(paper.chunks)
    result = enrich_paper(paper, data, db)

    status = "PDF" if result["downloaded"] else ("RICHER" if result["chunks_after"] > chunks_before else "same")
    if result["downloaded"]: pdf_dl += 1
    if status != "same": improved += 1

    print(f"[{status}] [{paper.id}] {paper.title[:50]}")
    if data:
        print(f"       arxiv={data.get('arxiv_id')} doi={data.get('doi')} pdf_url={bool(data.get('pdf_url'))}")
        print(f"       tldr={data.get('tldr','')[:60] if data.get('tldr') else 'none'}")
    print(f"       chunks: {chunks_before} -> {result['chunks_after']}  method={result['method']}")
    print()

print(f"Result: {improved}/{len(sample)} improved | {pdf_dl} PDF downloaded")
db.close()
