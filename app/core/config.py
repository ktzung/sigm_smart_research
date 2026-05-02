from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # ── Active provider ──────────────────────────────────────────────────────
    # Options: openai | perplexity | anthropic | gemini | ollama | minimax | openai_compat
    llm_provider: str = "openai"

    # ── OpenAI (default) ─────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # ── Perplexity ───────────────────────────────────────────────────────────
    perplexity_api_key: str = ""
    perplexity_model: str = "sonar-pro"          # or sonar, sonar-reasoning

    # ── Anthropic Claude ─────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-20241022"  # fast + cheap

    # ── MiniMax ─────────────────────────────────────────────────────────────
    minimax_api_key: str = ""
    minimax_model: str = "MiniMax-M2.7"
    minimax_base_url: str = "https://api.minimax.io/v1"

    # ── Google Gemini ────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # ── Ollama (local) ───────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.2"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./research_platform.db"

    # ── External APIs ────────────────────────────────────────────────────────
    semantic_scholar_api_key: str = ""
    ieee_api_key: str = ""
    grammarly_client_id: str = ""
    grammarly_client_secret: str = ""

    # ── Auth ─────────────────────────────────────────────────────────────────
    secret_key: str = "changeme-use-a-long-random-string-in-production"
    algorithm: str = "HS256"
    access_token_expire_hours: int = 24
    refresh_token_expire_days: int = 30

    # ── GitHub Integration ───────────────────────────────────────────────────
    encryption_key: str = "changeme-use-a-long-random-string-for-github-tokens"
    github_api_token: str = ""  # Optional: increases rate limit from 60 to 5000 req/hr

    # ── Email (SMTP) ──────────────────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@chimcanhcut.local"

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    max_papers_per_query: int = 40
    pdf_download_dir: str = "./storage/pdfs"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

Path(settings.pdf_download_dir).mkdir(parents=True, exist_ok=True)
