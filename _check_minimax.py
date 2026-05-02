"""Verify MiniMax key and OpenAI-compatible routing.

Run: python _check_minimax.py
"""
import sys

from app.core.config import settings
from app.core.llm_router import _build_client, _strip_json_fences


def _mask(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 12:
        return f"{value[:4]}..."
    return f"{value[:8]}...{value[-4:]}"


key = settings.minimax_api_key
base_url = settings.minimax_base_url
model = settings.minimax_model

print(f"MiniMax config: base_url={base_url} model={model} key={_mask(key)}")

if not key or "your-" in key or key == "":
    print("FAIL: MINIMAX_API_KEY is still a placeholder in .env")
    sys.exit(1)

print("Testing live API call...")
try:
    client, resolved_model = _build_client("minimax", model)
    resp = client.chat.completions.create(
        model=resolved_model,
        messages=[
            {"role": "system", "content": "Reply with a short acknowledgement."},
            {"role": "user", "content": "Reply with OK."},
        ],
        max_tokens=60,
        temperature=0,
    )
    raw = resp.choices[0].message.content or ""
    print(f"Raw response: {raw!r}")
    cleaned = _strip_json_fences(raw).strip()
    if not cleaned:
        raise RuntimeError("MiniMax returned an empty response")
    print("LLM call OK — MiniMax responded successfully")
except Exception as exc:
    print(f"LLM call FAIL: {exc}")
    sys.exit(1)

print("RESULT: MiniMax is ready to use")