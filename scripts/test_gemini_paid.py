"""Test all Gemini models after billing activation - find best for deep research."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.core import config as cfg
from openai import OpenAI

client = OpenAI(
    api_key=cfg.settings.gemini_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

# Research-relevant prompt to test quality, not just availability
RESEARCH_PROMPT = (
    "In 2-3 sentences, explain the key challenge of concept drift "
    "in federated learning and one promising solution approach."
)

# Priority order for deep research use case
CANDIDATES = [
    ("gemini-3.1-pro-preview",        "Gemini 3.1 Pro   - latest, best reasoning"),
    ("gemini-3-pro-preview",           "Gemini 3 Pro     - strong reasoning"),
    ("gemini-2.5-pro",                 "Gemini 2.5 Pro   - stable, large context"),
    ("gemini-3.1-flash-lite-preview",  "Gemini 3.1 Flash - fast, cost-efficient"),
    ("gemini-3-flash-preview",         "Gemini 3 Flash   - fast, good quality"),
    ("gemini-2.5-flash",               "Gemini 2.5 Flash - reliable baseline"),
]

print(f"Key: {cfg.settings.gemini_api_key[:12]}...")
print(f"Testing {len(CANDIDATES)} models...\n")

results = []
for model, desc in CANDIDATES:
    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a research assistant."},
                {"role": "user", "content": RESEARCH_PROMPT},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        elapsed = time.time() - t0
        text = resp.choices[0].message.content.strip()
        print(f"[PASS] {desc}")
        print(f"       {text[:120]}...")
        print(f"       latency: {elapsed:.1f}s\n")
        results.append((model, desc, True, elapsed, text))
    except Exception as e:
        msg = str(e)
        reason = "quota=0 (billing)" if "limit: 0" in msg else "rate_limit" if "429" in msg else msg[:60]
        print(f"[FAIL] {desc}")
        print(f"       {reason}\n")
        results.append((model, desc, False, 0, reason))
    time.sleep(3)

print("=" * 60)
print("SUMMARY - Models available for deep research:")
print("=" * 60)
working = [(m, d, lat, txt) for m, d, ok, lat, txt in results if ok]
failed  = [(m, d, txt) for m, d, ok, lat, txt in results if not ok]

for m, d, lat, _ in working:
    print(f"  ✅ {d:<45} ({lat:.1f}s)")
for m, d, reason in failed:
    print(f"  ❌ {d:<45} {reason}")

if working:
    best_model, best_desc, _, _ = working[0]
    print(f"\n→ Recommended: {best_model}")
    print(f"  ({best_desc})")
