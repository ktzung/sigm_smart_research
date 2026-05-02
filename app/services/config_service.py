"""
Config service — reads/writes LLM configuration from settings and .env file.
"""
import os
import tempfile
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.schemas.profile import ConfigGuiRead, ConfigSaveRequest

# Default path to the .env file
_DEFAULT_ENV_PATH = Path("research_platform") / ".env"


def _resolve_env_path(env_path: Optional[Path] = None) -> Path:
    """Resolve the .env file path, falling back to the default."""
    if env_path is not None:
        return env_path
    # Try to detect from settings model_config
    env_file = getattr(settings.model_config, "env_file", None)
    if env_file:
        p = Path(env_file)
        if p.exists():
            return p
    # Fall back to default
    if _DEFAULT_ENV_PATH.exists():
        return _DEFAULT_ENV_PATH
    return _DEFAULT_ENV_PATH


def get_config_gui() -> ConfigGuiRead:
    """Return current config state with API keys masked as booleans."""
    return ConfigGuiRead(
        llm_provider=settings.llm_provider,
        openai_model=settings.openai_model,
        perplexity_model=settings.perplexity_model,
        anthropic_model=settings.anthropic_model,
        gemini_model=settings.gemini_model,
        ollama_model=settings.ollama_model,
        ollama_base_url=settings.ollama_base_url,
        groq_model=settings.groq_model,
        has_openai_key=bool(settings.openai_api_key),
        has_perplexity_key=bool(settings.perplexity_api_key),
        has_anthropic_key=bool(settings.anthropic_api_key),
        has_gemini_key=bool(settings.gemini_api_key),
        has_groq_key=bool(settings.groq_api_key),
        has_minimax_key=bool(getattr(settings, 'minimax_api_key', None)),
        minimax_model=getattr(settings, 'minimax_model', None),
        minimax_base_url=getattr(settings, 'minimax_base_url', None),
    )


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict of key → value pairs."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            # Skip comments and blank lines
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                # Strip optional surrounding quotes from value
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                result[key] = value
    return result


def write_env_atomic(path: Path, data: dict[str, str]) -> None:
    """
    Merge `data` into the existing .env file and write atomically.

    - Reads existing .env (if present)
    - Merges: new non-None/non-empty values override existing keys
    - Writes to a temp file in the same directory, then os.replace() for atomicity
    """
    existing = parse_env_file(path)

    # Merge: only update keys that have non-empty values in data
    merged = dict(existing)
    for key, value in data.items():
        if value is not None and value != "":
            merged[key] = value

    # Write to temp file in same directory (required for os.replace to be atomic)
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".env.tmp.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for key, value in merged.items():
                f.write(f"{key}={value}\n")
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file if rename failed
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def save_config(data: ConfigSaveRequest, env_path: Optional[Path] = None) -> None:
    """
    Write non-empty config values to the .env file and reload settings.

    Raises OSError/IOError on filesystem failure (caller should catch and return HTTP 500).
    """
    path = _resolve_env_path(env_path)

    # Build dict of fields to write (only non-None, non-empty string values)
    field_map = {
        "LLM_PROVIDER": data.llm_provider,
        "OPENAI_MODEL": data.openai_model,
        "PERPLEXITY_MODEL": data.perplexity_model,
        "ANTHROPIC_MODEL": data.anthropic_model,
        "GEMINI_MODEL": data.gemini_model,
        "OLLAMA_MODEL": data.ollama_model,
        "OLLAMA_BASE_URL": data.ollama_base_url,
        "GROQ_MODEL": data.groq_model,
        "OPENAI_API_KEY": data.openai_api_key,
        "PERPLEXITY_API_KEY": data.perplexity_api_key,
        "ANTHROPIC_API_KEY": data.anthropic_api_key,
        "GEMINI_API_KEY": data.gemini_api_key,
        "GROQ_API_KEY": data.groq_api_key,
        "MINIMAX_MODEL": data.minimax_model,
        "MINIMAX_BASE_URL": data.minimax_base_url,
        "MINIMAX_API_KEY": data.minimax_api_key,
    }

    updates: dict[str, str] = {
        k: v for k, v in field_map.items() if v is not None and v != ""
    }

    write_env_atomic(path, updates)

    # Reload settings so changes take effect without server restart
    _reload_settings(path)


def _reload_settings(env_path: Path) -> None:
    """Reload the global settings object from the .env file."""
    from pydantic_settings import BaseSettings

    # Re-instantiate Settings with the updated env file
    # pydantic-settings v2: pass env_file via model_config override
    class _ReloadedSettings(type(settings)):
        model_config = {"env_file": str(env_path), "extra": "ignore"}

    new_settings = _ReloadedSettings()

    # Update the module-level singleton in-place by copying all field values
    for field_name in settings.model_fields:
        try:
            setattr(settings, field_name, getattr(new_settings, field_name))
        except Exception:
            pass
