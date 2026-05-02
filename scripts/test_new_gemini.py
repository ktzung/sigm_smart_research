import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.core import config as cfg, llm_router

# Test new Gemini key with the configured model
model = cfg.settings.gemini_model
key_preview = cfg.settings.gemini_api_key[:12] + "..."
print(f"Key : {key_preview}")
print(f"Model: {model}")
print("Testing...")

from openai import OpenAI
client = OpenAI(
    api_key=cfg.settings.gemini_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)
try:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "In one sentence, what is federated learning?"},
        ],
        temperature=0.3,
        max_tokens=100,
    )
    print(f"[PASS] {resp.choices[0].message.content.strip()}")
except Exception as e:
    print(f"[FAIL] {type(e).__name__}: {e}")
    # Also check available models for this key
    import httpx
    r = httpx.get(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={cfg.settings.gemini_api_key}",
        timeout=10
    )
    if r.status_code == 200:
        models = [m['name'] for m in r.json().get('models', [])
                  if 'generateContent' in m.get('supportedGenerationMethods', [])]
        print(f"\nAvailable models for this key ({len(models)}):")
        for m in sorted(models): print(f"  {m}")
    else:
        print(f"Could not list models: {r.status_code}")
