import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.core import llm as llm_module, config as cfg_module

models = [
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
]

cfg_module.settings.llm_provider = "gemini"
for model in models:
    cfg_module.settings.gemini_model = model
    llm_module.reset_llm()
    try:
        resp = llm_module.get_llm().complete(
            "You are a helpful assistant.",
            "In one sentence, what is federated learning?",
            max_tokens=80,
        )
        print(f"[PASS] {model}")
        print(f"       {resp.strip()[:150]}")
    except Exception as e:
        print(f"[FAIL] {model}: {str(e)[:120]}")
    time.sleep(5)
