"""Analyze the 38 skipped (already parsed) papers - what data do they have?"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

from app.core.database import SessionLocal
from app.models.topic import Topic
from app.models.paper import Paper, PaperChunk

db = SessionLocal()
topic = db.query(Topic).first()
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]

skipped = [p for p in included if p.parsed]
print(f"Skipped (already parsed): {len(skipped)}")
print()

# Categorize by chunk quality
good, abstract_only, empty = [], [], []
for p in skipped:
    chunks = p.chunks
    total_text = sum(len(c.text) for c in chunks)
    sections = set(c.section for c in chunks)
    if len(chunks) > 5 and total_text > 1000:
        good.append((p, len(chunks), total_text, sections))
    elif len(chunks) == 1 and "abstract" in sections:
        abstract_only.append((p, len(chunks), total_text))
    else:
        empty.append((p, len(chunks), total_text))

print(f"[GOOD]          Full PDF parsed  : {len(good)} papers")
print(f"[ABSTRACT ONLY] Abstract fallback: {len(abstract_only)} papers")
print(f"[POOR]          Empty/minimal    : {len(empty)} papers")

if abstract_only:
    print(f"\nAbstract-only papers (need better ingestion):")
    for p, nc, nt in abstract_only[:10]:
        print(f"  [{p.id}] {p.title[:60]}")
        print(f"         chunks={nc} chars={nt} pdf_url={'yes' if p.pdf_url else 'no'}")

if empty:
    print(f"\nEmpty/minimal papers:")
    for p, nc, nt in empty[:5]:
        print(f"  [{p.id}] {p.title[:60]} chunks={nc} chars={nt}")

db.close()
