"""Application configuration — loaded from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    app_name: str = "Auto Deck API"
    app_version: str = "0.1.0"
    debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./autodeck.db"

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    log_level: str = "INFO"

    ppt_output_dir: str = "data/output_ppt"
    template_decks_dir: str = "data/template_decks"

    TESTING_ENV: str = "AUTODECK"

    # NVIDIA NIM (free-tier, OpenAI-compatible)
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_max_tokens: int = 1024
    nvidia_temperature: float = 0.7

    # LLM orchestration (falls back to nvidia_* when empty)
    llm_provider: str = "nvidia_nim"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # Agent pipeline
    agent_max_retries: int = 3
    agent_timeout_seconds: int = 120
    agent_default_mode: str = "full"

    # Feature flags
    agent_mode_enabled: bool = True
    mcp_enabled: bool = False
    agent_metrics_enabled: bool = True

    # Data ingestion uploads
    upload_dir: str = "data/uploads"
    upload_ttl_seconds: int = 3600
    max_upload_size_mb: int = 50

    table_negative_number_style: str = "parentheses"
    table_numeric_string_allow_commas: bool = True
    table_total_row_label: str = "TOTAL"
    table_total_row_display: str = "TOTAL"
    table_total_row_preserve_input_casing: bool = True
    table_total_row_match_case_insensitive: bool = True
    table_total_row_strip_markdown: bool = True


settings = Settings()
