"""
LLM Cost Tracking Service.

Pricing table (USD per 1M tokens, input/output) — updated April 2026.
Sources: official provider pricing pages.
"""
import logging
import time
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

# ── Pricing table: (input_per_1M, output_per_1M) in USD ──────────────────────
# Content was paraphrased for compliance with licensing restrictions.
PRICING: dict[str, tuple[float, float]] = {
    # Gemini (Google AI Studio / Vertex AI pay-as-you-go, prompts ≤200K tokens)
    "gemini/gemini-3.1-pro-preview":        (2.00,  12.00),
    "gemini/gemini-3.1-flash-lite-preview": (0.10,   0.40),
    "gemini/gemini-2.5-pro-preview-06-05":  (1.25,  10.00),
    "gemini/gemini-2.0-flash":              (0.10,   0.40),
    "gemini/gemini-3.1-pro":                (2.00,  12.00),
    "gemini/gemini-3.1-flash":              (0.50,   3.00),

    # Perplexity Sonar
    "perplexity/sonar-pro":                 (3.00,  15.00),
    "perplexity/sonar":                     (1.00,   1.00),
    "perplexity/sonar-reasoning":           (1.00,   5.00),
    "perplexity/sonar-reasoning-pro":       (2.00,   8.00),

    # Anthropic Claude
    "anthropic/claude-opus-4-5":            (15.00, 75.00),
    "anthropic/claude-sonnet-4-5":          (3.00,  15.00),
    "anthropic/claude-3-5-haiku-20241022":  (0.80,   4.00),

    # OpenAI
    "openai/gpt-4o":                        (2.50,  10.00),
    "openai/gpt-4o-mini":                   (0.15,   0.60),
    "openai/o3":                            (10.00, 40.00),

    # Ollama — local, no cost
    "ollama/*":                             (0.00,   0.00),

    # Groq — fast inference (free tier available, paid very cheap)
    "groq/llama-3.3-70b-versatile":         (0.59,   0.79),
    "groq/llama-4-scout-17b-16e-instruct":  (0.11,   0.34),
    "groq/deepseek-r1-distill-llama-70b":   (0.75,   0.99),
    "groq/qwen-qwq-32b":                    (0.29,   0.39),
    "groq/*":                               (0.50,   0.80),
}

# Free tier models (Gemini free tier via AI Studio)
FREE_TIER_MODELS = {
    "gemini-3.1-flash-lite-preview",
    "gemini-2.0-flash",
    "gemini-3.1-pro-preview",  # has free tier with rate limits
}


def get_price(provider: str, model: str) -> tuple[float, float]:
    """Return (input_per_1M, output_per_1M) for a provider/model pair."""
    key = f"{provider}/{model}"
    if key in PRICING:
        return PRICING[key]
    # Wildcard match (e.g. ollama/*)
    wildcard = f"{provider}/*"
    if wildcard in PRICING:
        return PRICING[wildcard]
    # Fallback: estimate based on provider
    fallback = {
        "gemini": (0.50, 3.00),
        "openai": (2.50, 10.00),
        "anthropic": (3.00, 15.00),
        "perplexity": (1.00, 5.00),
        "ollama": (0.00, 0.00),
    }
    return fallback.get(provider, (1.00, 5.00))


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost in USD for a single LLM call."""
    input_rate, output_rate = get_price(provider, model)
    cost = (prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate
    return round(cost, 8)


def extract_token_counts(provider: str, response_obj) -> tuple[int, int]:
    """
    Extract (prompt_tokens, completion_tokens) from a provider response object.
    Handles OpenAI-compatible and Anthropic response formats.
    """
    try:
        if provider == "anthropic":
            # Anthropic: response.usage.input_tokens / output_tokens
            usage = getattr(response_obj, "usage", None)
            if usage:
                return getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0)
        else:
            # OpenAI-compatible: response.usage.prompt_tokens / completion_tokens
            usage = getattr(response_obj, "usage", None)
            if usage:
                return getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0)
    except Exception:
        pass
    return 0, 0


# ── Context vars for tracking current stage/topic/user ───────────────────────
_current_stage_ctx: ContextVar[str] = ContextVar("current_stage", default="unknown")
_current_topic_ctx: ContextVar[int | None] = ContextVar("current_topic_id", default=None)
_current_user_ctx: ContextVar[int | None] = ContextVar("current_user_id", default=None)


def set_tracking_context(stage: str, topic_id: int | None = None, user_id: int | None = None):
    """Set context for the current pipeline stage execution."""
    _current_stage_ctx.set(stage)
    _current_topic_ctx.set(topic_id)
    _current_user_ctx.set(user_id)


def record_usage(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int | None = None,
    stage: str | None = None,
    topic_id: int | None = None,
    user_id: int | None = None,
) -> float:
    """
    Record LLM usage to DB. Returns estimated cost in USD.
    Uses context vars if stage/topic_id/user_id not provided.
    """
    stage = stage or _current_stage_ctx.get()
    topic_id = topic_id if topic_id is not None else _current_topic_ctx.get()
    user_id = user_id if user_id is not None else _current_user_ctx.get()

    total_tokens = prompt_tokens + completion_tokens
    cost = estimate_cost(provider, model, prompt_tokens, completion_tokens)

    try:
        from app.core.database import SessionLocal
        from app.models.llm_usage import LLMUsageRecord
        db = SessionLocal()
        try:
            record = LLMUsageRecord(
                user_id=user_id,
                topic_id=topic_id,
                stage=stage,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
            )
            db.add(record)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to record LLM usage: %s", e)

    logger.debug(
        "LLM usage: %s/%s stage=%s tokens=%d+%d cost=$%.6f",
        provider, model, stage, prompt_tokens, completion_tokens, cost,
    )
    return cost
