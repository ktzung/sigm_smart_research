"""
Task-aware LLM router with dynamic model selection.

Task categories and recommended models:
  search          → Perplexity sonar-pro (web-aware, real-time)
  fast_screen     → GPT-4o-mini / Gemini Flash (cheap, high-throughput)
  deep_analysis   → GPT-4o / Gemini 2.5 Pro (long-context reasoning)
  writing         → GPT-4o (academic prose)
  coding          → GPT-4o-mini (structured JSON/code)

Override priority (highest → lowest):
  1. Per-stage topic override   topic.model_routing_overrides["stage:<stage>"]
  2. Per-category topic override topic.model_routing_overrides["category:<cat>"]
  3. Global LLM_PROVIDER setting
  4. STAGE_ROUTING default
  5. Fallback chain
"""
import logging
import re
from typing import Optional
from contextvars import ContextVar
from app.core.config import settings

logger = logging.getLogger(__name__)

# Context variable — set before calling pipeline stages to inject topic overrides
_topic_routing_ctx: ContextVar[dict] = ContextVar("topic_routing_overrides", default={})

# LLM call timeout in seconds
_LLM_TIMEOUT = 60

# ── Model catalog ─────────────────────────────────────────────────────────────
MODEL_CATALOG: dict[str, list[dict]] = {
    "openai": [
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "context_k": 128,
            "cost": "high",
            "best_for": ["writing", "coding", "deep_analysis"],
            "description": "Strong writing and structured output",
        },
        {
            "id": "gpt-4o-mini",
            "name": "GPT-4o Mini",
            "context_k": 128,
            "cost": "low",
            "best_for": ["fast_screen", "coding"],
            "description": "Fast and cheap, good for extraction and screening",
        },
        {
            "id": "o3",
            "name": "OpenAI o3",
            "context_k": 200,
            "cost": "very_high",
            "best_for": ["deep_analysis"],
            "description": "Best reasoning model for complex analysis",
        },
    ],
    "anthropic": [
        {
            "id": "claude-opus-4-5",
            "name": "Claude Opus 4.5",
            "context_k": 200,
            "cost": "high",
            "best_for": ["deep_analysis", "writing"],
            "description": "Best for complex reasoning, synthesis, long-document analysis",
        },
        {
            "id": "claude-sonnet-4-5",
            "name": "Claude Sonnet 4.5",
            "context_k": 200,
            "cost": "medium",
            "best_for": ["writing", "coding"],
            "description": "Best for academic writing, code generation, structured output",
        },
        {
            "id": "claude-3-5-haiku-20241022",
            "name": "Claude Haiku 3.5",
            "context_k": 200,
            "cost": "low",
            "best_for": ["fast_screen"],
            "description": "Fast and cheap, good for screening and simple tasks",
        },
    ],
    "gemini": [
        {
            "id": "gemini-2.5-pro-preview-06-05",
            "name": "Gemini 2.5 Pro",
            "context_k": 1000,
            "cost": "high",
            "best_for": ["deep_analysis"],
            "description": "1M context window, best for cross-paper synthesis",
        },
        {
            "id": "gemini-2.5-flash-preview-05-20",
            "name": "Gemini 2.5 Flash",
            "context_k": 1000,
            "cost": "low",
            "best_for": ["fast_screen", "coding"],
            "description": "Fast and cheap, good for screening and extraction",
        },
        {
            "id": "gemini-2.0-flash",
            "name": "Gemini 2.0 Flash",
            "context_k": 128,
            "cost": "low",
            "best_for": ["fast_screen", "coding"],
            "description": "Stable fast model, good for screening",
        },
    ],
    "minimax": [
        {
            "id": "MiniMax-M2.7",
            "name": "MiniMax M2.7",
            "context_k": 200,
            "cost": "medium",
            "best_for": ["deep_analysis", "writing", "coding"],
            "description": "MiniMax coding and reasoning model for Claude Code-style workflows",
        },
        {
            "id": "MiniMax-M2.5-highspeed",
            "name": "MiniMax M2.5 Highspeed",
            "context_k": 128,
            "cost": "low",
            "best_for": ["fast_screen", "coding"],
            "description": "Fast MiniMax variant for high-throughput tasks",
        },
    ],
    "groq": [],  # not in use
    "perplexity": [
        {
            "id": "sonar-pro",
            "name": "Sonar Pro",
            "context_k": 128,
            "cost": "medium",
            "best_for": ["search"],
            "description": "Web-aware search with real-time paper discovery",
        },
        {
            "id": "sonar",
            "name": "Sonar",
            "context_k": 128,
            "cost": "low",
            "best_for": ["search"],
            "description": "Lightweight web search",
        },
    ],
}

# ── Task category → default (provider, model) ─────────────────────────────────
CATEGORY_DEFAULTS: dict[str, tuple[str, str]] = {
    "search":        ("perplexity", "sonar-pro"),
    "fast_screen":   ("openai",     "gpt-4o-mini"),
    "deep_analysis": ("openai",     "gpt-4o"),
    "writing":       ("anthropic",  "claude-sonnet-4-5"),  # upgraded: Claude for academic writing
    "coding":        ("openai",     "gpt-4o-mini"),
}

# ── Per-stage routing table ───────────────────────────────────────────────────
# Each entry: (provider, model, temperature, max_tokens, task_category)
STAGE_ROUTING: dict[str, tuple[str, str, float, int, str]] = {
    "query_plan":       ("openai",     "gpt-4o-mini",       0.3, 2048, "search"),
    "discover":         ("perplexity", "sonar-pro",         0.3, 2048, "search"),
    "screen":           ("openai",     "gpt-4o-mini",       0.1,  512, "fast_screen"),
    "ingest":           ("openai",     "gpt-4o-mini",       0.1,  256, "fast_screen"),
    "extract":          ("openai",     "gpt-4o-mini",       0.1, 2048, "coding"),
    "prisma":           ("openai",     "gpt-4o-mini",       0.3, 4096, "fast_screen"),
    "citation_network": ("openai",     "gpt-4o-mini",       0.1,  256, "fast_screen"),
    "quality_check":    ("openai",     "gpt-4o-mini",       0.3, 4096, "fast_screen"),
    "export_latex":     ("openai",     "gpt-4o-mini",       0.1,  512, "coding"),
    # Writing stages: upgraded to Claude Sonnet 4.5 for quality
    "synthesize":       ("anthropic",  "claude-sonnet-4-5", 0.3, 8192, "writing"),
    "taxonomy":         ("anthropic",  "claude-sonnet-4-5", 0.3, 8192, "writing"),
    "gaps":             ("anthropic",  "claude-sonnet-4-5", 0.3, 8192, "writing"),
    "idea_generation":  ("anthropic",  "claude-sonnet-4-5", 0.7, 4096, "writing"),  # NEW
    "draft":            ("anthropic",  "claude-sonnet-4-5", 0.5, 8192, "writing"),
    "review":           ("anthropic",  "claude-sonnet-4-5", 0.2, 4096, "writing"),
    "revision":         ("anthropic",  "claude-sonnet-4-5", 0.4, 8192, "writing"),
    # Remote stages
    "stage16":          ("openai",     "gpt-4o",            0.4, 8192, "deep_analysis"),
    "stage17":          ("openai",     "gpt-4o",            0.3, 8192, "coding"),
    "stage18":          ("openai",     "gpt-4o-mini",       0.2, 4096, "coding"),
    "stage22":          ("openai",     "gpt-4o",            0.3, 8192, "writing"),
}

# Fallback order when the primary provider/model fails
FALLBACK_CHAIN: list[tuple[str, str]] = [
    ("openai", "gpt-4o-mini"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences that LLMs sometimes wrap around JSON output."""
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _build_client(provider: str, model: str):
    """Return (client, model) for the given provider."""
    from openai import OpenAI

    if provider == "openai":
        return OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=_LLM_TIMEOUT,
        ), model

    if provider == "gemini":
        return OpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=_LLM_TIMEOUT,
        ), model

    if provider == "perplexity":
        return OpenAI(
            api_key=settings.perplexity_api_key,
            base_url="https://api.perplexity.ai",
            timeout=_LLM_TIMEOUT,
        ), model

    if provider == "anthropic":
        import anthropic
        return anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=_LLM_TIMEOUT,
        ), model

    if provider == "minimax":
        return OpenAI(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            timeout=_LLM_TIMEOUT,
        ), model

    if provider == "ollama":
        return OpenAI(
            api_key="ollama",
            base_url=settings.ollama_base_url,
            timeout=_LLM_TIMEOUT,
        ), model

    if provider == "openai_compat":
        return OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=_LLM_TIMEOUT,
        ), model

    raise ValueError(f"Unknown provider: {provider!r}")


def _apply_global_provider(
    provider: str, model: str, category: str
) -> tuple[str, str]:
    """
    If LLM_PROVIDER is set to something other than 'openai', redirect all
    non-search stages to that provider's configured model.
    Perplexity is only used for 'search' category stages.
    """
    global_provider = settings.llm_provider.lower()

    if global_provider == "openai" or global_provider == provider:
        return provider, model

    # Keep search stages on their dedicated web-aware provider by default.
    # Global MiniMax routing still applies to the rest of the pipeline.
    if global_provider in {"perplexity", "minimax"} and category == "search":
        return provider, model

    provider_model_map: dict[str, str] = {
        "gemini":        settings.gemini_model or "gemini-2.0-flash",
        "anthropic":     settings.anthropic_model or "claude-3-5-haiku-20241022",
        "ollama":        settings.ollama_model or "llama3.2",
        "minimax":       settings.minimax_model or "MiniMax-M2.7",
        "openai_compat": settings.openai_model or "gpt-4o",
        "perplexity":    settings.perplexity_model or "sonar-pro",
    }

    if global_provider in provider_model_map:
        return global_provider, provider_model_map[global_provider]

    return provider, model


def resolve_model_for_stage(
    stage: str,
    topic_overrides: Optional[dict] = None,
) -> tuple[str, str, float, int]:
    """
    Resolve (provider, model, temperature, max_tokens) for a stage.
    See module docstring for override priority.
    """
    entry = STAGE_ROUTING.get(stage)
    if entry:
        provider, model, temperature, max_tokens, category = entry
    else:
        provider, model, temperature, max_tokens, category = (
            "openai", settings.openai_model or "gpt-4o", 0.3, 4096, "writing"
        )

    if topic_overrides:
        stage_key = f"stage:{stage}"
        cat_key = f"category:{category}"
        if stage_key in topic_overrides:
            ov = topic_overrides[stage_key]
            provider = ov.get("provider", provider)
            model = ov.get("model", model)
            # Topic override applied — skip global provider override
            return provider, model, temperature, max_tokens
        elif cat_key in topic_overrides:
            ov = topic_overrides[cat_key]
            provider = ov.get("provider", provider)
            model = ov.get("model", model)
            return provider, model, temperature, max_tokens

    # No topic override — apply global LLM_PROVIDER setting
    provider, model = _apply_global_provider(provider, model, category)
    return provider, model, temperature, max_tokens


# ── Router ────────────────────────────────────────────────────────────────────

class TaskRouter:
    """Routes each pipeline stage to the optimal LLM, with per-topic overrides."""

    def complete_for_stage(
        self,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        provider_override: Optional[str] = None,
        model_override: Optional[str] = None,
        topic_overrides: Optional[dict] = None,
    ) -> str:
        # Merge context-var overrides with call-level overrides
        effective_overrides = {**_topic_routing_ctx.get(), **(topic_overrides or {})}

        provider, model, temperature, max_tokens = resolve_model_for_stage(
            stage, effective_overrides or None
        )

        # Explicit call-level overrides (highest priority — tests / admin)
        if provider_override:
            provider = provider_override
        if model_override:
            model = model_override

        # Build attempt list: primary first, then fallbacks (skip duplicates)
        primary = (provider, model)
        attempts = [primary] + [
            (p, m) for p, m in FALLBACK_CHAIN if (p, m) != primary
        ]

        last_error: Exception | None = None
        for attempt_provider, attempt_model in attempts:
            try:
                result = self._call(
                    attempt_provider, attempt_model,
                    system_prompt, user_prompt,
                    temperature, max_tokens,
                )
                if (attempt_provider, attempt_model) != primary:
                    logger.warning(
                        "Stage '%s': fell back from %s/%s → %s/%s",
                        stage, provider, model, attempt_provider, attempt_model,
                    )
                else:
                    logger.debug("Stage '%s': used %s/%s", stage, provider, model)
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Stage '%s': %s/%s failed — %s: %s",
                    stage, attempt_provider, attempt_model, type(exc).__name__, exc,
                )

        raise RuntimeError(
            f"All LLM providers failed for stage '{stage}'. Last error: {last_error}"
        ) from last_error

    def _call(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Single LLM call — no internal retry (handled by complete_for_stage)."""
        import time
        from app.services.cost_tracker import extract_token_counts, record_usage

        client, model = _build_client(provider, model)
        t0 = time.monotonic()

        if provider == "anthropic":
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens or 4096,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            prompt_tok, completion_tok = extract_token_counts(provider, response)
            record_usage(provider, model, prompt_tok, completion_tok, latency_ms)
            return response.content[0].text

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        prompt_tok, completion_tok = extract_token_counts(provider, response)
        record_usage(provider, model, prompt_tok, completion_tok, latency_ms)
        return response.choices[0].message.content or ""


# ── Singleton ─────────────────────────────────────────────────────────────────

_router_instance: Optional[TaskRouter] = None


def get_router() -> TaskRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = TaskRouter()
    return _router_instance


def reset_router() -> None:
    global _router_instance
    _router_instance = None
