"""Application configuration — loaded from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    app_name: str = "DeckBuilder API"
    app_version: str = "0.1.0"
    debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./deckbuilder.db"

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    log_level: str = "INFO"

    ppt_output_dir: str = "data/output_ppt"
    template_decks_dir: str = "data/template_decks"

    TESTING_ENV: str = "DECKBUILDER"

    table_negative_number_style: str = "parentheses"
    table_numeric_string_allow_commas: bool = True
    table_total_row_label: str = "TOTAL"
    table_total_row_display: str = "TOTAL"
    table_total_row_preserve_input_casing: bool = True
    table_total_row_match_case_insensitive: bool = True
    table_total_row_strip_markdown: bool = True


settings = Settings()
