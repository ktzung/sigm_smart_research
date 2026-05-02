import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.api.pipeline_ops import router

for r in router.routes:
    if hasattr(r, 'methods'):
        method = list(r.methods)[0]
        print(f"  {method:<6} {r.path}")
