import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.core.config import settings
from app.core.llm_router import STAGE_ROUTING

def _has_value(value: str) -> bool:
    return bool(value) and "your-" not in value


working = {
    provider
    for provider, ok in {
        'openai': _has_value(settings.openai_api_key),
        'perplexity': _has_value(settings.perplexity_api_key),
        'anthropic': _has_value(settings.anthropic_api_key),
        'gemini': _has_value(settings.gemini_api_key),
        'minimax': _has_value(settings.minimax_api_key),
        'ollama': True,
    }.items()
    if ok
}
print("\nFinal routing table:")
print(f"  {'Stage':<12} {'Provider':<12} {'Model':<38} {'Status'}")
print("  " + "-" * 78)
for stage, (p, m, t, mt, *_) in STAGE_ROUTING.items():
    status = "OK" if p in working else "QUOTA EXCEEDED"
    print(f"  {stage:<12} {p:<12} {m:<38} {status}")
print()
