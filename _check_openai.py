"""Verify OpenAI key works for the screen stage. Run: python _check_openai.py"""
import os, sys

from app.core.config import settings
from app.core.llm_router import resolve_model_for_stage, _build_client, _strip_json_fences
import json

# ── 1. Key presence ───────────────────────────────────────────────────────────
p, m, t, mt = resolve_model_for_stage("screen")
print(f"Screen stage routes to: {p}/{m}  (temp={t}, max_tokens={mt})")

key = settings.openai_api_key
if not key or "your-" in key or key == "":
    print("FAIL: OPENAI_API_KEY is still a placeholder in .env")
    sys.exit(1)
print(f"Key present: {key[:8]}...{key[-4:]}")

# ── 2. Live API call ──────────────────────────────────────────────────────────
print("\nTesting live API call...")
try:
    client, model = _build_client("openai", m)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a paper screener. Return only valid JSON."},
            {"role": "user",   "content": 'Return exactly: {"label":"direct","relevance_score":0.9,"reason":"test ok"}'},
        ],
        max_tokens=60,
        temperature=0,
    )
    raw = resp.choices[0].message.content or ""
    print(f"Raw response: {raw!r}")
    parsed = json.loads(_strip_json_fences(raw))
    assert parsed.get("label") == "direct", f"Unexpected label: {parsed}"
    print("LLM call OK — JSON parsed correctly")
except Exception as e:
    print(f"LLM call FAIL: {e}")
    sys.exit(1)

# ── 3. Fallback chain check ───────────────────────────────────────────────────
from app.core.llm_router import FALLBACK_CHAIN
print(f"\nFallback chain: {FALLBACK_CHAIN}")
groq_key = settings.groq_api_key
if groq_key and "your-" not in groq_key:
    print("Groq fallback: key set")
else:
    print("Groq fallback: no key — if OpenAI fails, no fallback available")

print("\nRESULT: Screen stage is ready to run")
