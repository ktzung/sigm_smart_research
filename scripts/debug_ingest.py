"""Debug ingest stage - run directly to see actual error."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

from app.core.database import SessionLocal
from app.models.topic import Topic
from app.models.paper import Paper
from app.services.ingestion import ingest_paper

db = SessionLocal()
topic = db.query(Topic).first()

# Get included papers (non-excluded)
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
print(f"Total papers    : {len(topic.papers)}")
print(f"Included papers : {len(included)}")
print(f"Already parsed  : {sum(1 for p in included if p.parsed)}")
print(f"PDF downloaded  : {sum(1 for p in included if p.pdf_downloaded)}")
print(f"Has pdf_url     : {sum(1 for p in included if p.pdf_url)}")
print()

# Try ingesting first 3 papers and show result
print("Testing ingest on first 3 included papers:")
for paper in included[:3]:
    print(f"\n  [{paper.id}] {paper.title[:60]}")
    print(f"       pdf_url   : {paper.pdf_url}")
    print(f"       parsed    : {paper.parsed}")
    try:
        result = ingest_paper(paper, db)
        print(f"       result    : {result}")
    except Exception as e:
        print(f"       ERROR     : {type(e).__name__}: {e}")

db.close()
