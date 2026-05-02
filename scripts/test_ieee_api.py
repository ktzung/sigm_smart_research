"""
Test IEEE Xplore API:
1. Metadata API - search by DOI
2. Open Access API - check if any papers are OA
3. DOI batch lookup
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()

import httpx
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.topic import Topic
from app.services.fulltext_enrichment import _s2_batch_enrich

IEEE_BASE = "https://ieeexploreapi.ieee.org/api/v1"
KEY = settings.ieee_api_key
print(f"IEEE API Key: {KEY[:8]}...\n")

db = SessionLocal()
topic = db.query(Topic).first()
included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
abstract_only = [p for p in included if p.parsed and len(p.chunks) <= 1]
print(f"Abstract-only papers: {len(abstract_only)}")

# Get DOIs from S2 batch
print("Fetching DOIs from S2...")
s2_data = _s2_batch_enrich(abstract_only, db)
doi_map = {p.id: s2_data[p.id]["doi"] for p in abstract_only
           if p.id in s2_data and s2_data[p.id].get("doi")}
print(f"Papers with DOI: {len(doi_map)}/{len(abstract_only)}\n")

# ── Test 1: DOI API (batch up to 25) ─────────────────────────────────────────
print("=" * 55)
print("TEST 1: IEEE DOI API (batch lookup)")
print("=" * 55)
sample_dois = list(doi_map.values())[:5]
doi_str = ",".join(sample_dois)
try:
    resp = httpx.get(
        f"{IEEE_BASE}/articles/doi",
        params={"apikey": KEY, "doi": doi_str},
        timeout=15,
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        articles = data.get("articles", [])
        print(f"Found: {len(articles)} articles")
        for art in articles[:3]:
            print(f"  Title: {art.get('title','')[:55]}")
            print(f"  access_type: {art.get('access_type','')}")
            print(f"  pdf_url: {art.get('pdf_url','none')}")
            print(f"  abstract_url: {art.get('abstract_url','')}")
            print()
    else:
        print(f"Error: {resp.text[:300]}")
except Exception as e:
    print(f"ERROR: {e}")

# ── Test 2: Open Access API ───────────────────────────────────────────────────
print("=" * 55)
print("TEST 2: IEEE Open Access API")
print("=" * 55)
# Search for our topic
try:
    resp = httpx.get(
        f"{IEEE_BASE}/articles/search",
        params={
            "apikey": KEY,
            "querytext": "federated learning concept drift",
            "open_access": "True",
            "max_records": 10,
            "start_record": 1,
        },
        timeout=15,
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        total = data.get("total_records", 0)
        articles = data.get("articles", [])
        print(f"Total OA results: {total}")
        for art in articles[:5]:
            print(f"  [{art.get('access_type','')}] {art.get('title','')[:55]}")
            print(f"    pdf_url: {art.get('pdf_url','none')[:60]}")
    else:
        print(f"Error: {resp.text[:300]}")
except Exception as e:
    print(f"ERROR: {e}")

# ── Test 3: Check existing papers by DOI for OA status ───────────────────────
print()
print("=" * 55)
print("TEST 3: Check OA status of existing IEEE papers")
print("=" * 55)
ieee_dois = [(pid, doi) for pid, doi in doi_map.items()
             if "10.1109" in doi or "10.48550" in doi][:10]
print(f"IEEE DOIs to check: {len(ieee_dois)}")

oa_found = 0
for pid, doi in ieee_dois[:5]:
    try:
        resp = httpx.get(
            f"{IEEE_BASE}/articles/doi",
            params={"apikey": KEY, "doi": doi},
            timeout=10,
        )
        if resp.status_code == 200:
            arts = resp.json().get("articles", [])
            if arts:
                art = arts[0]
                access = art.get("access_type", "unknown")
                pdf = art.get("pdf_url", "")
                if access == "open_access" or pdf:
                    oa_found += 1
                print(f"  [{access}] doi={doi[:40]}")
                print(f"    pdf={pdf[:60] if pdf else 'none'}")
        time.sleep(0.2)
    except Exception as e:
        print(f"  ERROR: {e}")

print(f"\nOA papers found: {oa_found}/{min(5, len(ieee_dois))}")
db.close()
