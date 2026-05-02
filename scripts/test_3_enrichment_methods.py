"""
Test 3 enrichment methods - fixed version:
  1. Semantic Scholar: batch endpoint (100 papers/req, no rate limit issue)
  2. Unpaywall: extract DOI from S2 externalIds, not just URL
  3. arXiv: fix URL encoding, use proper API format
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

import httpx
from app.core.database import SessionLocal
from app.models.topic import Topic
from app.core.config import settings
from app.models.paper import PaperSource

db = SessionLocal()
topic = db.query(Topic).first()
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
abstract_only = [p for p in included if p.parsed and len(p.chunks) <= 1]
print(f"Abstract-only papers: {len(abstract_only)}\n")

sample = abstract_only[:5]

# ── Method 1: S2 Batch API ────────────────────────────────────────────────────
print("=" * 55)
print("METHOD 1: Semantic Scholar BATCH API")
print("=" * 55)
s2_headers = {"Content-Type": "application/json"}
if settings.semantic_scholar_api_key:
    s2_headers["x-api-key"] = settings.semantic_scholar_api_key
    print(f"  API key: {settings.semantic_scholar_api_key[:8]}...")
else:
    print("  No API key (batch endpoint has higher free limits)")

paper_ids = [p.external_id for p in sample if p.external_id]
try:
    resp = httpx.post(
        "https://api.semanticscholar.org/graph/v1/paper/batch",
        headers=s2_headers,
        params={"fields": "abstract,tldr,openAccessPdf,externalIds"},
        json={"ids": paper_ids},
        timeout=15,
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        results = resp.json()
        s2_pdf, s2_richer, s2_arxiv = 0, 0, 0
        for i, (paper, data) in enumerate(zip(sample, results)):
            if not data:
                print(f"  [NULL] [{paper.id}] {paper.title[:45]}")
                continue
            pdf_url  = (data.get("openAccessPdf") or {}).get("url")
            richer   = len(data.get("abstract") or "") > len(paper.abstract or "")
            arxiv_id = (data.get("externalIds") or {}).get("ArXiv")
            tldr     = (data.get("tldr") or {}).get("text", "")
            if pdf_url:  s2_pdf += 1
            if richer:   s2_richer += 1
            if arxiv_id: s2_arxiv += 1
            print(f"  [OK] [{paper.id}] {paper.title[:45]}")
            print(f"       pdf={'YES '+pdf_url[:40] if pdf_url else 'no'}")
            print(f"       arxiv_id={arxiv_id}  richer={richer}")
            print(f"       tldr={tldr[:80] if tldr else 'none'}")
        print(f"\n  Result: {s2_pdf}/5 PDF | {s2_richer}/5 richer abstract | {s2_arxiv}/5 arXiv ID")
    else:
        print(f"  Error: {resp.text[:200]}")
except Exception as e:
    print(f"  ERROR: {e}")

# ── Method 2: Unpaywall via DOI from S2 raw_data ─────────────────────────────
print()
print("=" * 55)
print("METHOD 2: Unpaywall via DOI (from S2 raw_data)")
print("=" * 55)

# Extract DOI from PaperSource raw_data
doi_map = {}
for paper in abstract_only:
    for src in paper.sources:
        raw = src.raw_data or {}
        ext_ids = raw.get("externalIds") or {}
        doi = ext_ids.get("DOI")
        if doi:
            doi_map[paper.id] = doi
            break

print(f"  Papers with DOI in raw_data: {len(doi_map)}/{len(abstract_only)}")

unp_ok, unp_pdf = 0, 0
doi_sample = [(p, doi_map[p.id]) for p in abstract_only if p.id in doi_map][:5]
for paper, doi in doi_sample:
    try:
        resp = httpx.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": "research@example.com"},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            best = data.get("best_oa_location") or {}
            pdf_url = best.get("url_for_pdf")
            unp_ok += 1
            if pdf_url: unp_pdf += 1
            print(f"  [OK] [{paper.id}] {paper.title[:45]}")
            print(f"       oa={data.get('oa_status')} pdf={pdf_url[:60] if pdf_url else 'none'}")
        else:
            print(f"  [FAIL {resp.status_code}] doi={doi}")
    except Exception as e:
        print(f"  [ERROR] {e}")
    time.sleep(0.3)

if not doi_sample:
    print("  No DOIs found in raw_data - S2 discovery didn't store externalIds")
print(f"\n  Result: {unp_ok}/{len(doi_sample)} OK | {unp_pdf} PDF found")

# ── Method 3: arXiv title search (fixed) ─────────────────────────────────────
print()
print("=" * 55)
print("METHOD 3: arXiv title search (fixed)")
print("=" * 55)

import urllib.parse, xml.etree.ElementTree as ET

arx_found, arx_pdf = 0, 0
for paper in sample:
    # Clean title for search
    clean_title = paper.title[:60].replace('"', '').replace("'", "")
    query = f'ti:"{clean_title}"'
    encoded = urllib.parse.quote(query)
    url = f"https://export.arxiv.org/api/query?search_query={encoded}&max_results=1&sortBy=relevance"
    try:
        resp = httpx.get(url, timeout=12, headers={"User-Agent": "research-bot/1.0"})
        if resp.status_code != 200 or not resp.text.strip():
            print(f"  [FAIL {resp.status_code}] [{paper.id}] {paper.title[:40]}")
            continue
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if entries:
            entry = entries[0]
            found_title = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
            pdf_link = next((l.get("href") for l in entry.findall("atom:link", ns)
                             if l.get("type") == "application/pdf"), None)
            arxiv_id = entry.findtext("atom:id", "", ns).split("/abs/")[-1]
            # Fuzzy title match: check if >50% of words overlap
            words_paper = set(paper.title.lower().split())
            words_found = set(found_title.lower().split())
            overlap = len(words_paper & words_found) / max(len(words_paper), 1)
            match = overlap > 0.5
            arx_found += 1
            if match and pdf_link: arx_pdf += 1
            print(f"  [{'MATCH' if match else 'WEAK'}] [{paper.id}] {paper.title[:40]}")
            print(f"       found : {found_title[:55]}")
            print(f"       overlap={overlap:.0%} arxiv_id={arxiv_id} pdf={bool(pdf_link)}")
        else:
            print(f"  [NOT FOUND] [{paper.id}] {paper.title[:45]}")
    except Exception as e:
        print(f"  [ERROR] [{paper.id}]: {type(e).__name__}: {e}")
    time.sleep(0.5)

print(f"\n  Result: {arx_found}/5 found | {arx_pdf} matched with PDF")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 55)
print("SUMMARY & RECOMMENDATION")
print("=" * 55)
print(f"  S2 Batch   : {'OK' if resp.status_code == 200 else 'FAIL'} - best for PDF URLs + richer abstracts")
print(f"  Unpaywall  : needs DOI - {len(doi_map)} papers have DOI")
print(f"  arXiv      : {arx_found}/5 found - good for arXiv papers")
print()
print("  Recommended integration order:")
print("  1. S2 batch (get openAccessPdf + arXiv ID)")
print("  2. arXiv PDF download (for papers with arXiv ID)")
print("  3. Unpaywall (for papers with DOI)")

db.close()
