import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
import httpx
from app.core.config import settings

# Test S2 API directly on one paper
paper_id = "12feb11afa7201c32c7603be98e28fa8aed267e5"
headers = {}
if settings.semantic_scholar_api_key:
    headers["x-api-key"] = settings.semantic_scholar_api_key

url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
params = {"fields": "title,abstract,tldr,openAccessPdf,externalIds"}

try:
    resp = httpx.get(url, params=params, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Title: {data.get('title','')[:60]}")
    print(f"Abstract len: {len(data.get('abstract') or '')}")
    print(f"TLDR: {data.get('tldr')}")
    print(f"openAccessPdf: {data.get('openAccessPdf')}")
    print(f"externalIds: {data.get('externalIds')}")
except Exception as e:
    print(f"ERROR: {e}")
