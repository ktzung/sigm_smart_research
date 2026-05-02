"""Startup health check — run with: python _check.py"""
import os, sys, json
os.environ.setdefault("DATABASE_URL", "sqlite:///./research_platform.db")

errors = []

# ── 1. Config ────────────────────────────────────────────────────────────────
try:
    from app.core.config import settings
    print(f"[OK] config  provider={settings.llm_provider}  db={settings.database_url[:45]}")
except Exception as e:
    errors.append(f"[FAIL] config: {e}")

# ── 2. Database ──────────────────────────────────────────────────────────────
try:
    from app.core.database import init_db
    init_db()
    print("[OK] database  schema created/verified")
except Exception as e:
    errors.append(f"[FAIL] database: {e}")

# ── 3. LLM router ────────────────────────────────────────────────────────────
try:
    from app.core.llm_router import resolve_model_for_stage, _strip_json_fences
    for stage in ["screen", "synthesize", "draft", "discover"]:
        p, m, t, mt = resolve_model_for_stage(stage)
        print(f"[OK] router   {stage:<20} -> {p}/{m}")
except Exception as e:
    errors.append(f"[FAIL] router: {e}")

# ── 4. JSON fence stripping ──────────────────────────────────────────────────
try:
    from app.core.llm_router import _strip_json_fences
    plain  = '{"label":"direct","relevance_score":0.9,"reason":"ok"}'
    fenced = "```json\n" + plain + "\n```"
    assert json.loads(_strip_json_fences(plain))["label"]  == "direct"
    assert json.loads(_strip_json_fences(fenced))["label"] == "direct"
    print("[OK] json_fence  plain + fenced both parse correctly")
except Exception as e:
    errors.append(f"[FAIL] json_fence: {e}")

# ── 5. Full app import (routes + startup hooks) ──────────────────────────────
try:
    from main import app
    route_paths = [r.path for r in app.routes]
    api_count   = sum(1 for r in route_paths if "/api/v1" in r)
    print(f"[OK] app     {len(route_paths)} routes  ({api_count} under /api/v1)")
    assert "/health" in route_paths, "/health missing"
except Exception as e:
    errors.append(f"[FAIL] app: {e}")

# ── 6. Screening imports ─────────────────────────────────────────────────────
try:
    from app.services.screening import screen_paper, screen_all_papers, _rule_based_prefilter
    print("[OK] screening  imports OK")
except Exception as e:
    errors.append(f"[FAIL] screening: {e}")

# ── 7. API key warnings ──────────────────────────────────────────────────────
placeholders = {
    "OPENAI_API_KEY":  settings.openai_api_key,
    "GROQ_API_KEY":    settings.groq_api_key,
    "GEMINI_API_KEY":  settings.gemini_api_key,
}
for name, val in placeholders.items():
    if not val or "your-" in val:
        print(f"[WARN] {name} is not set — LLM calls will fail until you add a real key")

# ── Summary ──────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"RESULT: {len(errors)} error(s) found:")
    for e in errors:
        print(" ", e)
    sys.exit(1)
else:
    print("RESULT: all checks passed — server is ready to start")
    print()
    print("  Run with:  uvicorn main:app --reload --port 8000")
