"""Run full enrichment on all 84 abstract-only papers with S2 API key."""
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

print(f"Enriching all {len(abstract_only)} abstract-only papers with S2 API key...\n")

# S2 batch - all at once
s2_data = _s2_batch_enrich(abstract_only, db)
print(f"S2 returned data for: {len(s2_data)}/{len(abstract_only)} papers")

has_arxiv  = sum(1 for d in s2_data.values() if d.get("arxiv_id"))
has_doi    = sum(1 for d in s2_data.values() if d.get("doi"))
has_oa_pdf = sum(1 for d in s2_data.values() if d.get("pdf_url"))
print(f"  Has arXiv ID  : {has_arxiv}")
print(f"  Has DOI       : {has_doi}")
print(f"  Has OA PDF URL: {has_oa_pdf}")
print()

# Run enrichment
improved, pdf_dl, richer = 0, 0, 0
for paper in abstract_only:
    data = s2_data.get(paper.id)
    chunks_before = len(paper.chunks)
    result = enrich_paper(paper, data, db)
    if result["downloaded"]:
        pdf_dl += 1
        improved += 1
        print(f"  [PDF {result['chunks_after']} chunks] [{paper.id}] {paper.title[:55]}")
    elif result["chunks_after"] > chunks_before:
        richer += 1
        improved += 1

print(f"\n{'='*50}")
print(f"DONE: {len(abstract_only)} papers processed")
print(f"  PDF downloaded  : {pdf_dl}")
print(f"  Richer abstract : {richer}")
print(f"  Total improved  : {improved}")
print(f"  Still abstract  : {len(abstract_only) - improved}")

# Final stats
all_included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
full_pdf  = sum(1 for p in all_included if p.pdf_downloaded)
multi_chunk = sum(1 for p in all_included if len(p.chunks) > 5)
print(f"\nOverall corpus ({len(all_included)} included papers):")
print(f"  Full PDF parsed : {full_pdf}")
print(f"  Multi-chunk     : {multi_chunk}")
print(f"  Abstract only   : {len(all_included) - multi_chunk}")

db.close()
