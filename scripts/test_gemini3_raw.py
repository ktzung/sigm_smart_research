"""Test Gemini Pro models directly without retry wrapper to see raw error."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.core import config as cfg_module
from openai import OpenAI

key = cfg_module.settings.gemini_api_key
client = OpenAI(
    api_key=key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

models = ["gemini-3-pro-preview", "gemini-3.1-pro-preview"]

for model in models:
    print(f"\nTesting {model}...")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "In one sentence, what is federated learning?"},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        print(f"  [PASS] {resp.choices[0].message.content.strip()[:150]}")
    except Exception as e:
        # Print full error details
        print(f"  [FAIL] {type(e).__name__}")
        print(f"         {e}")
        if hasattr(e, 'status_code'):
            print(f"         status_code: {e.status_code}")
        if hasattr(e, 'body'):
            print(f"         body: {e.body}")
    time.sleep(5)
