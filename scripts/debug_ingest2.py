"""Check ingest progress in detail."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

from app.core.database import SessionLocal
from app.models.topic import Topic
from app.models.paper import Paper, PaperChunk

db = SessionLocal()
topic = db.query(Topic).first()
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]

parsed   = [p for p in included if p.parsed]
unparsed = [p for p in included if not p.parsed]
has_pdf  = [p for p in included if p.pdf_downloaded]
has_url  = [p for p in included if p.pdf_url]

print(f"Included papers : {len(included)}")
print(f"Parsed          : {len(parsed)}  <- progress so far")
print(f"Unparsed        : {len(unparsed)}  <- still pending")
print(f"PDF downloaded  : {len(has_pdf)}")
print(f"Has pdf_url     : {len(has_url)}")

# Check if any paper is stuck mid-download (has pdf_url but not downloaded)
stuck_download = [p for p in included if p.pdf_url and not p.pdf_downloaded and not p.parsed]
if stuck_download:
    print(f"\nPossibly stuck on PDF download ({len(stuck_download)} papers):")
    for p in stuck_download[:5]:
        print(f"  [{p.id}] {p.title[:60]}")
        print(f"         url: {p.pdf_url[:80] if p.pdf_url else 'none'}")

# Show first few unparsed
if unparsed:
    print(f"\nFirst 5 unparsed papers:")
    for p in unparsed[:5]:
        print(f"  [{p.id}] {p.title[:60]}")
        print(f"         pdf_url: {'yes' if p.pdf_url else 'no'} | parsed: {p.parsed}")

db.close()
