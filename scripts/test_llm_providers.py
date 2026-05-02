"""Test Perplexity and Gemini API keys from .env"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core import llm as llm_module
from app.core import config as cfg_module

TEST_PROMPT = "Reply with exactly: OK"

def test_provider(provider, model):
    print(f"\n{'='*50}")
    print(f"Testing: {provider} / {model}")
    print('='*50)
    try:
        cfg_module.settings.llm_provider = provider
        if provider == "perplexity":
            cfg_module.settings.perplexity_model = model
        elif provider == "gemini":
            cfg_module.settings.gemini_model = model
        llm_module.reset_llm()
        llm = llm_module.get_llm()
        result = llm.complete("You are a test assistant.", TEST_PROMPT, max_tokens=20)
        print(f"[PASS] Response: {result.strip()}")
        return True
    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
        return False

results = {}

# Test Perplexity
results["perplexity/sonar-pro"] = test_provider("perplexity", "sonar-pro")

# Test Gemini
results["gemini/gemini-2.0-flash"] = test_provider("gemini", "gemini-2.0-flash")

print(f"\n{'='*50}")
print("SUMMARY")
print('='*50)
for name, ok in results.items():
    status = "[PASS]" if ok else "[FAIL]"
    print(f"  {status}  {name}")
