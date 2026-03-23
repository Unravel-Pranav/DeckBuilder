from pydantic import Field, model_validator
import os
import json
from datetime import datetime
from typing import ClassVar, Dict, Any
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from hello.vault import print_vault_token


class Settings(BaseSettings):
    # Load env vars case-insensitively so AWS_BUCKET / OIDC_ISSUER etc. are picked up
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)
    # development environment
    env: str = os.getenv("ENV") or "test"
    # Database
    database_url_test: str = (
        "postgresql+asyncpg://postgres:hello@localhost:5432/cbredb"  # overwritten by .env
    )
    database_url_dev: str = (
        "postgresql+asyncpg://postgres:hello@cbre-db:5432/cbredb"  # overwritten by .env
    )
    database_url_qa: str = (
        "postgresql+asyncpg://postgres:hello@cbre-db:5432/cbredb"  # overwritten by .env
    )
    database_url_prod: str = (
        "postgresql+asyncpg://postgres:hello@cbre-db:5432/cbredb"  # overwritten by .env
    )

    @property
    def database_url(self) -> str:
        """Returns the appropriate database URL based on the dev flag."""
        env = os.getenv('ENV')
        if env == "test": 
            return self.database_url_test 
        elif env == "dev":
            return self.database_url_dev
        elif env == "qa":
            return self.database_url_qa
        elif env == "prod":
            return self.database_url_prod
        else:
            return self.database_url_test


    # Schema
    app_schema_test: str = "public"
    app_schema_qa: str = "market_reports"
    app_schema_dev: str = "market_reports_stg"
    app_schema_prod: str = "market_reports"

    @property
    def app_schema(self) -> str:
        """Returns the appropriate database schema based on the dev flag."""
        env = os.getenv('ENV')
        if env == "test":
            return self.app_schema_test
        elif env == "dev":
            return self.app_schema_dev 
        elif env == "qa":
            return self.app_schema_qa
        elif env == "prod":
            return self.app_schema_prod
        else:
            return self.app_schema_test

    # S3
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    aws_region: str | None = None
    aws_bucket: str | None = None

    # Snowflake (optional for now)
    snowflake_account: str | None = None
    snowflake_user: str | None = None
    snowflake_role: str | None = None
    snowflake_private_key_path: str | None = None
    snowflake_private_key_passphrase: str | None = None
    snowflake_warehouse: str | None = None
    snowflake_database: str | None = None
    snowflake_schema: str | None = None

    # SMTP (optional)
    smtp_host: str | None = None
    smtp_port: int | None = None  # 587 for STARTTLS, 465 for SSL
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_from_email: str | None = None

    APP_SIGNING_SECRET: str = "change-me"
    APP_JWT_EXPIRES_HOURS: int = 12
    APP_SESSION_COOKIE_NAME: str = "app_session"
    COOKIE_SECURE: bool = False
    SESSION_SECRET: str = os.getenv("OIDC_CLIENT_SECRET") or "dev-session-secret"
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    
    # Public endpoints that skip authentication (list of path patterns)
    PUBLIC_ENDPOINTS: list[str] = ["/reports/download", "/auth/login", "/auth/callback", "/health", "/docs", "/openapi.json"]

    # Application timezone for scheduling (IANA name, e.g., "UTC", "America/Los_Angeles")
    app_timezone: str | None = "UTC"

    # Database SSL - some environments require encrypted connections (asyncpg expects
    # an `ssl` parameter). Set to true in env for those environments.
    database_ssl: bool = False
    # Optional: allow explicit sslmode string if the underlying driver/url needs it
    database_ssl_mode: str | None = None

    # OIDC (generic; works for Okta/Auth0/Azure AD, etc.)
    OIDC_ISSUER: str | None = None
    
    OIDC_CLIENT_ID_TEST: str | None = None
    OIDC_CLIENT_ID_DEV: str | None = None
    OIDC_CLIENT_ID_QA: str | None = None
    OIDC_CLIENT_ID_PROD: str | None = None
    OIDC_CLIENT_ID: str | None = Field(
        default_factory=lambda data: data.get(
            f"OIDC_CLIENT_ID_{(os.getenv('ENV') or '').upper()}"
        )
        or data.get("OIDC_CLIENT_ID")
    )
    OIDC_CLIENT_SECRET_TEST: str | None = None
    OIDC_CLIENT_SECRET_DEV: str | None = None
    OIDC_CLIENT_SECRET_QA: str | None = None
    OIDC_CLIENT_SECRET_PROD: str | None = None
    OIDC_CLIENT_SECRET: str | None = Field(
        default_factory=lambda data: data.get(
            f"OIDC_CLIENT_SECRET_{(os.getenv('ENV') or '').upper()}"
        )
        or data.get("OIDC_CLIENT_SECRET")
    )
    OIDC_SCOPES: str | None = "openid email profile"
    OIDC_LOGOUT_URL: str | None = None

    # MIQ
    MIQ_BASE: str = "https://marketiq.cbre.com"
    MIQ_RBAC_TOKEN: str | None = None  # env/secret per UAT/Prod 
    MIQ_BASE_QA: str =  "https://qa.marketiq.cbre.com" 
    MIQ_RBAC_TOKEN_QA: str | None = None
    MIQ_ROLES_PATH: str = "/api/users/{user_id}/roles"
    MIQ_MARKETS_PATH: str = "/api/users/{user_id}/perms/location"
    PERM_TTL_MIN: int = 500

    # LOGGING
    BASE_DIR_ENV: ClassVar[str | None] = os.getenv("LOG_BASE_DIR") or os.getenv("LOG_DIR")
    ARCHIVE_DIR_ENV: ClassVar[str | None] = os.getenv("LOG_ARCHIVE_DIR")
    MAX_BYTES: ClassVar[int] = int(os.getenv("LOG_MAX_BYTES", 10 * 1024 * 1024))
    BACKUP_COUNT: ClassVar[int] = int(os.getenv("LOG_BACKUP_COUNT", 5))
    CONSOLE_LEVEL: ClassVar[str] = os.getenv("LOG_CONSOLE_LEVEL", "INFO").upper()
    INFO_FILENAME: ClassVar[str] = "info.log"
    ERROR_FILENAME: ClassVar[str] = "error.log"
    CURRENT_DATE: ClassVar[str] = datetime.utcnow().strftime("%Y-%m-%d")
    LOG_FORMAT: ClassVar[str] = os.getenv("LOG_FORMAT", "%(asctime)s %(levelname)s %(name)s: %(message)s")
    DISABLE_DEBUG_LOGS: ClassVar[bool] = os.getenv("LOG_DISABLE_DEBUG", "true").lower() in {"1", "true", "yes"}
    # Testing Env
    TESTING_ENV: str = "CBRE"

    # =========================================================================
    # Table formatting (PPT tables)
    # =========================================================================
    # How to render negative numbers in tables.
    # - "parentheses": -1234 -> "(1,234)"
    # - "minus": keep "-1,234"
    table_negative_number_style: str = "parentheses"

    # Whether numeric strings with thousands separators should be treated as numeric.
    # Example: "-1,234" -> "(1,234)" when table_negative_number_style="parentheses"
    table_numeric_string_allow_commas: bool = True

    # TOTAL row formatting (PPT tables)
    # If the first cell of a row is exactly this label (after optional markdown stripping and
    # whitespace normalization), the entire row will be forced to bold.
    table_total_row_label: str = "TOTAL"
    # What to display in the first cell when the TOTAL row is detected. This lets us
    # normalize inputs like "**TOTAL**" to plain "TOTAL" in the PPT output.
    table_total_row_display: str = "TOTAL"
    # If true, the first cell text for TOTAL rows will preserve the input casing after
    # markdown stripping and whitespace normalization. If false, the configured
    # table_total_row_display will be used.
    table_total_row_preserve_input_casing: bool = True
    table_total_row_match_case_insensitive: bool = True
    table_total_row_strip_markdown: bool = True

    # LLM Config
    OPENAI_API_KEY: str | None = None

    # LLM Model Providers
    LLM_MODEL_PROVIDERS: str = "WSO2_OPENAI,WSO2_BEDROCK.WSO2_GEMINI"

    # =========================================================================
    # Azure OpenAI Configuration (via WSO2 Gateway)
    # =========================================================================
    # Used when LLM_PROVIDER=WSO2_OPENAI to access Go Azure OpenAI models
    # via WSO2 Gateway
    # =========================================================================

    # WSO2 OpenAI Configuration
    WSO2_OPENAI_API_ENDPOINT: str | None = None
    WSO2_OPENAI_AUTH_ENDPOINT: str | None = None
    WSO2_OPENAI_CLIENT_ID: str | None = None
    WSO2_OPENAI_CLIENT_SECRET: str | None = None
    WSO2_OPENAI_API_VERSION: str | None = None
    WSO2_OPENAI_MODELS: str = "gpt-5.1"
    WSO2_OPENAI_TIMEOUT: int = 600
    WSO2_OPENAI_MAX_RETRIES: int = 3

    # =========================================================================
    # AWS Bedrock Configuration (for WSO2_CLAUDE provider)
    # =========================================================================
    # Used when LLM_MODEL_PROVIDER=WSO2_CLAUDE to access Claude models
    # via AWS Bedrock through WSO2 Gateway
    # =========================================================================

    # WSO2 Bedrock Configuration
    WSO2_BEDROCK_API_ENDPOINT: str | None = None
    WSO2_BEDROCK_AUTH_ENDPOINT: str | None = None
    WSO2_BEDROCK_CLIENT_ID: str | None = None
    WSO2_BEDROCK_CLIENT_SECRET: str | None = None
    WSO2_BEDROCK_DEPLOYMENT_ID: str | None = None
    WSO2_BEDROCK_MODELS: str = "claude-sonnet-4.5"
    WSO2_BEDROCK_TIMEOUT: int = 600
    WSO2_BEDROCK_MAX_RETRIES: int = 3
    WSO2_BEDROCK_THINKING_BUDGET_LOW: int = 2000
    WSO2_BEDROCK_THINKING_BUDGET_MEDIUM: int = 5000
    WSO2_BEDROCK_THINKING_BUDGET_HIGH: int = 10000

    # =========================================================================
    # Google Gemini Configuration (via WSO2 Gateway)
    # =========================================================================
    # Used when LLM_PROVIDER=WSO2_GEMINI to access Google Gemini models
    # via WSO2 Gateway
    # =========================================================================
    
    # WSO2 Gemini Configuration
    WSO2_GEMINI_API_ENDPOINT: str | None = None
    WSO2_GEMINI_AUTH_ENDPOINT: str | None = None
    WSO2_GEMINI_CLIENT_ID: str | None = None
    WSO2_GEMINI_CLIENT_SECRET: str | None = None
    WSO2_GEMINI_MODELS: str = "gemini-3-pro-preview"
    WSO2_GEMINI_TIMEOUT: int = 600
    WSO2_GEMINI_MAX_RETRIES: int = 3

    # WSO2 Token and LLM retry configuration
    WSO2_TOKEN_MAX_RETRIES: int = 5
    WSO2_TOKEN_BACKOFF_INITIAL: float = 5
    WSO2_TOKEN_BACKOFF_MAX: float = 60.0
    WSO2_TOKEN_BACKOFF_EXP_BASE: float = 2.0 # exponential base
    WSO2_LLM_MAX_RETRIES: int = 5
    WSO2_LLM_BACKOFF_INITIAL: float = 5
    WSO2_LLM_BACKOFF_MAX: float = 60.0
    WSO2_LLM_BACKOFF_EXP_BASE: float = 2.0 # exponential base

    # Default LLM Model Parameters
    LLM_MODEL_PROVIDER: str = "WSO2_OPENAI" # Options: WSO2_OPENAI, WSO2_BEDROCK, WSO2_GEMINI, OPENAI
    LLM_MODEL_NAME: str = "gpt-5.1"
    LLM_MODEL_TEMPERATURE: float = 0
    LLM_MODEL_THINKING_ENABLED: bool = False
    LLM_MODEL_REASONING_EFFECT: str = "high"
    LLM_MODEL_STREAMING: bool = False
    LLM_MODEL_MAX_TOKENS: int = 10000
    LLM_MODEL_TIMEOUT: int = 180
    LLM_MODEL_MAX_RETRIES: int = 3
    LLM_MODEL_API_VERSION: str = "2025-01-01-preview"
    # Exponential backoff configuration for LLM model operations
    LLM_MODEL_BACKOFF_INITIAL: float = 5
    LLM_MODEL_BACKOFF_MAX: float = 60.0
    LLM_MODEL_BACKOFF_EXP_BASE: float = 2.0
    LLM_MODEL_BACKOFF_JITTER: float = 0.5

    # Evaluation LLM Model Providers
    EVAL_MODEL_PROVIDER: str = "WSO2_OPENAI"
    EVAL_MODEL_NAME: str = "gpt-4o-mini"
    EVAL_MODEL_TEMPERATURE: float = 0
    EVAL_MODEL_THINKING_ENABLED: bool = False
    EVAL_MODEL_REASONING_EFFECT: str = "high"
    EVAL_MODEL_STREAMING: bool = False
    EVAL_MODEL_MAX_TOKENS: int = 100000
    EVAL_MODEL_TIMEOUT: int = 60
    EVAL_MODEL_MAX_RETRIES: int = 3
    EVAL_MODEL_API_VERSION: str = "2025-01-01-preview"
    # Exponential backoff configuration for LLM model operations
    EVAL_MODEL_BACKOFF_INITIAL: float = 5
    EVAL_MODEL_BACKOFF_MAX: float = 60.0
    EVAL_MODEL_BACKOFF_EXP_BASE: float = 2.0
    EVAL_MODEL_BACKOFF_JITTER: float = 0.5

    # Confidence Metric LLM Model Providers
    C_METRIC_MODEL_PROVIDER: str = "WSO2_OPENAI"
    C_METRIC_MODEL_NAME: str = "gpt-5.1"
    C_METRIC_MODEL_TEMPERATURE: float = 0
    C_METRIC_MODEL_THINKING_ENABLED: bool = False
    C_METRIC_MODEL_REASONING_EFFECT: str = "low"
    C_METRIC_MODEL_STREAMING: bool = False
    C_METRIC_MODEL_MAX_TOKENS: int = 100000
    C_METRIC_MODEL_TIMEOUT: int = 60
    C_METRIC_MODEL_MAX_RETRIES: int = 3
    C_METRIC_MODEL_API_VERSION: str = "2025-01-01-preview"
    # Exponential backoff configuration for LLM model operations
    C_METRIC_MODEL_BACKOFF_INITIAL: float = 5
    C_METRIC_MODEL_BACKOFF_MAX: float = 60.0
    C_METRIC_MODEL_BACKOFF_EXP_BASE: float = 2.0
    C_METRIC_MODEL_BACKOFF_JITTER: float = 0.5
    # Confidence metric level thresholds (0–100 scale)
    # Scores < CONFIDENCE_LOW_MAX -> "low"
    # Scores < CONFIDENCE_MEDIUM_MAX -> "medium"
    # Scores >= CONFIDENCE_MEDIUM_MAX -> "high"
    CONFIDENCE_LOW_MAX: float = 60.0
    CONFIDENCE_MEDIUM_MAX: float = 80.0

    LLM_PROMPT_VERSION: str = "v3"
    AGENTS_DEBUG: bool = False

    # Multi-Geography Report Generation
    # Property sub-types that support generating multiple reports per geography selection
    # (vacancy_index, submarket, district). When enabled, each geography selection
    # generates a separate report instead of combining them.
    MULTI_GEOGRAPHY_PROPERTY_SUB_TYPES: list[str] = ["submarket"]

    # Agent-wise Configuration
    # Individual environment variables for each agent configuration
    # Format: <agent_name>_<property>=<value>
    
    # Summary Agent
    summary_agent_enabled: str = "true"
    summary_agent_provider: str = "WSO2_OPENAI"
    summary_agent_model: str = "gpt-5.1"
    summary_agent_temperature: str = "0"
    summary_agent_thinking_enabled: str = "true"
    summary_agent_thinking_level: str = "high"
    summary_agent_streaming_enabled: str = "true"
    
    # Consolidation Agent
    consolidation_agent_enabled: str = "true"
    consolidation_agent_provider: str = "WSO2_OPENAI"
    consolidation_agent_model: str = "gpt-5.1"
    consolidation_agent_temperature: str = "0"
    consolidation_agent_thinking_enabled: str = "true"
    consolidation_agent_thinking_level: str = "high"
    consolidation_agent_streaming_enabled: str = "true"
    
    # Data Check Agent
    data_check_agent_enabled: str = "true"
    data_check_agent_provider: str = "WSO2_OPENAI"
    data_check_agent_model: str = "gpt-5.1"
    data_check_agent_temperature: str = "0"
    data_check_agent_thinking_enabled: str = "false"
    data_check_agent_thinking_level: str = "medium"
    data_check_agent_streaming_enabled: str = "false"
    
    # Unit Check Agent
    unit_check_agent_enabled: str = "true"
    unit_check_agent_provider: str = "WSO2_OPENAI"
    unit_check_agent_model: str = "gpt-5.1"
    unit_check_agent_temperature: str = "0"
    unit_check_agent_thinking_enabled: str = "false"
    unit_check_agent_thinking_level: str = "medium"
    unit_check_agent_streaming_enabled: str = "false"
    
    # Validation Agent
    validation_agent_enabled: str = "true"
    validation_agent_provider: str = "WSO2_OPENAI"
    validation_agent_model: str = "gpt-5.1"
    validation_agent_temperature: str = "0"
    validation_agent_thinking_enabled: str = "false"
    validation_agent_thinking_level: str = "medium"
    validation_agent_streaming_enabled: str = "false"

    # Title Generation Agent
    title_generation_agent_enabled: str = "true"
    title_generation_agent_provider: str = "WSO2_OPENAI"
    title_generation_agent_model: str = "gpt-5.1"
    title_generation_agent_temperature: str = "1.0"
    title_generation_agent_thinking_enabled: str = "false"
    title_generation_agent_thinking_level: str = "medium"
    title_generation_agent_streaming_enabled: str = "false"
    
    @property
    def agents_config(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns agent-wise configuration dictionary from individual environment variables.
        
        Constructs the dictionary from individual env vars like:
        - summary_agent_enabled, summary_agent_provider, etc.
        
        Returns:
            Dictionary containing agent configurations
        """
        def _parse_bool(value: str) -> bool:
            """Convert string to boolean."""
            return value.lower() in ("true", "1", "yes")
        
        def _parse_int(value: str) -> int:
            """Convert string to integer."""
            try:
                return int(value)
            except ValueError:
                return 0
        
        def _parse_float(value: str) -> float:
            """Convert string to float."""
            try:
                return float(value)
            except ValueError:
                return 0.0
        
        return {
            "summary_agent": {
                "enabled": _parse_bool(self.summary_agent_enabled),
                "provider": self.summary_agent_provider,
                "model": self.summary_agent_model,
                "temperature": _parse_float(self.summary_agent_temperature),
                "thinking_enabled": _parse_bool(self.summary_agent_thinking_enabled),
                "thinking_level": self.summary_agent_thinking_level, 
                "streaming_enabled": _parse_bool(self.summary_agent_streaming_enabled)
            },
            "consolidation_agent": {
                "enabled": _parse_bool(self.consolidation_agent_enabled),
                "provider": self.consolidation_agent_provider,
                "model": self.consolidation_agent_model,
                "temperature": _parse_float(self.consolidation_agent_temperature),
                "thinking_enabled": _parse_bool(self.consolidation_agent_thinking_enabled),
                "thinking_level": self.consolidation_agent_thinking_level, 
                "streaming_enabled": _parse_bool(self.consolidation_agent_streaming_enabled)
            },
            "data_check_agent": {
                "enabled": _parse_bool(self.data_check_agent_enabled),
                "provider": self.data_check_agent_provider,
                "model": self.data_check_agent_model,
                "temperature": _parse_float(self.data_check_agent_temperature),
                "thinking_enabled": _parse_bool(self.data_check_agent_thinking_enabled),
                "thinking_level": self.data_check_agent_thinking_level, 
                "streaming_enabled": _parse_bool(self.data_check_agent_streaming_enabled)
            },
            "unit_check_agent": {
                "enabled": _parse_bool(self.unit_check_agent_enabled),
                "provider": self.unit_check_agent_provider,
                "model": self.unit_check_agent_model,
                "temperature": _parse_float(self.unit_check_agent_temperature),
                "thinking_enabled": _parse_bool(self.unit_check_agent_thinking_enabled),
                "thinking_level": self.unit_check_agent_thinking_level, 
                "streaming_enabled": _parse_bool(self.unit_check_agent_streaming_enabled)
            },
            "validation_agent": {
                "enabled": _parse_bool(self.validation_agent_enabled),
                "provider": self.validation_agent_provider,
                "model": self.validation_agent_model,
                "temperature": _parse_float(self.validation_agent_temperature),
                "thinking_enabled": _parse_bool(self.validation_agent_thinking_enabled),
                "thinking_level": self.validation_agent_thinking_level, 
                "streaming_enabled": _parse_bool(self.validation_agent_streaming_enabled)
            },
            "title_generation_agent": {
                "enabled": _parse_bool(self.title_generation_agent_enabled),
                "provider": self.title_generation_agent_provider,
                "model": self.title_generation_agent_model,
                "temperature": _parse_float(self.title_generation_agent_temperature),
                "thinking_enabled": _parse_bool(self.title_generation_agent_thinking_enabled),
                "thinking_level": self.title_generation_agent_thinking_level,
                "streaming_enabled": _parse_bool(self.title_generation_agent_streaming_enabled)
            }
        }
    
    api_base_url_test: str = "http://localhost:5251/api"
    api_base_url_dev: str = "https://marketreports-dev.cdo.cbre.com/api/api"
    api_base_url_qa: str = "https://marketreports-qa.cdo.cbre.com/api/api"
    api_base_url_prod: str = "https://marketreports.cdo.cbre.com/api/api"

    api_base_url: str = Field(
        default_factory=lambda data: data[
            f"api_base_url_{(os.getenv('ENV') or 'test').lower()}"
        ]
    )

    @model_validator(mode="after")
    def _validate_signing_secret(cls, values):
        """Ensure a non-default signing secret outside of dev/test/local."""
        env_val = (values.env or "").lower()
        secret = values.APP_SIGNING_SECRET
        if env_val not in {"test", "dev", "local"}:
            if not secret or secret == "change-me":
                raise ValueError("APP_SIGNING_SECRET must be set to a non-default value")
        return values


def _resolve_runtime_env() -> str:
    return (os.getenv("ENV") or os.getenv("env") or "test").lower()


def _load_local_env() -> None:
    """
    Load the closest .env file.
    """
    load_dotenv(find_dotenv())


def _load_vault_env(env:str) -> None:
    secrets = print_vault_token(env)
    if not secrets:
        raise RuntimeError("Vault secrets unavailable; cannot start in non-test environment")
    for key, value in secrets.items():
        if value is None:
            continue
        os.environ[key] = str(value)


_runtime_env = _resolve_runtime_env()

#if _runtime_env == "test" or _runtime_env == 'dev': Uncomment this for DEV DB migration
if _runtime_env == "test":
    _load_local_env()
else:
    _load_vault_env(_runtime_env)
os.environ.setdefault("ENV", _runtime_env)

settings = Settings()
