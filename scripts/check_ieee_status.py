import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.services.ieee_enrichment import _ieee_key_active
from app.core.config import settings

print(f"IEEE key    : {settings.ieee_api_key[:8]}...")
print(f"IEEE active : {_ieee_key_active()}")
print(f"S2 key      : {settings.semantic_scholar_api_key[:8]}...")
print("All imports OK")
