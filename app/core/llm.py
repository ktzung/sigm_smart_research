"""
Pluggable LLM provider layer.

Supported providers (set LLM_PROVIDER in .env):
  - openai          : OpenAI GPT models (default)
  - perplexity      : Perplexity AI (sonar models, has web search built-in)
  - anthropic       : Anthropic Claude
  - gemini          : Google Gemini via OpenAI-compatible endpoint
  - ollama          : Local Ollama (no API key needed)
    - minimax         : MiniMax OpenAI-compatible endpoint
  - openai_compat   : Any OpenAI-compatible API (LM Studio, Together, etc.)
"""
import logging
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMProvider:
    def __init__(self):
        self._provider = settings.llm_provider
        self._model = settings.openai_model  # reused as generic model field
        self._client = self._build_client()

    def _build_client(self):
        p = self._provider

        if p == "openai":
            from openai import OpenAI
            return OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )

        elif p == "perplexity":
            # Perplexity uses OpenAI-compatible API
            from openai import OpenAI
            self._model = settings.perplexity_model
            return OpenAI(
                api_key=settings.perplexity_api_key,
                base_url="https://api.perplexity.ai",
            )

        elif p == "anthropic":
            # Wrap Anthropic SDK behind the same interface
            import anthropic
            self._model = settings.anthropic_model
            return anthropic.Anthropic(api_key=settings.anthropic_api_key)

        elif p == "minimax":
            # MiniMax exposes an OpenAI-compatible chat API
            from openai import OpenAI
            self._model = settings.minimax_model
            return OpenAI(
                api_key=settings.minimax_api_key,
                base_url=settings.minimax_base_url,
            )

        elif p == "gemini":
            # Google Gemini via OpenAI-compatible endpoint
            from openai import OpenAI
            self._model = settings.gemini_model
            return OpenAI(
                api_key=settings.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )

        elif p == "ollama":
            from openai import OpenAI
            self._model = settings.ollama_model
            return OpenAI(
                api_key="ollama",
                base_url=settings.ollama_base_url,
            )

        elif p == "openai_compat":
            # Generic OpenAI-compatible (LM Studio, Together AI, Groq, etc.)
            from openai import OpenAI
            return OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )

        else:
            raise ValueError(
                f"Unsupported LLM_PROVIDER: '{p}'. "
                "Choose: openai | perplexity | anthropic | gemini | ollama | minimax | openai_compat"
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: Optional[int] = 4096,
    ) -> str:
        logger.debug("LLM call | provider=%s | model=%s", self._provider, self._model)

        if self._provider == "anthropic":
            return self._complete_anthropic(system_prompt, user_prompt, temperature, max_tokens)

        # All other providers use OpenAI-compatible chat completions
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def _complete_anthropic(self, system_prompt, user_prompt, temperature, max_tokens):
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or 4096,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text


# Singleton
_llm_instance: Optional[LLMProvider] = None


def get_llm() -> LLMProvider:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMProvider()
    return _llm_instance


def reset_llm():
    """Force re-initialization (useful when config changes at runtime)."""
    global _llm_instance
    _llm_instance = None
