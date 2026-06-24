from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.

    All provider switches, API keys, thresholds, and feature flags are
    defined here. Change a provider by setting the corresponding *_PROVIDER
    env var — no code changes needed in any agent or business-logic file.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # =========================================================
    # APP
    # =========================================================
    app_env: str = Field(default="local", alias="APP_ENV")
    service_name: str = Field(default="baggage-claim-ai", alias="SERVICE_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")

    # =========================================================
    # PROVIDER SWITCHES  (swap without touching agent code)
    # =========================================================
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    vision_provider: str = Field(default="gemini", alias="VISION_PROVIDER")
    ocr_provider: str = Field(default="gemini", alias="OCR_PROVIDER")
    storage_provider: str = Field(default="local", alias="STORAGE_PROVIDER")
    db_provider: str = Field(default="supabase", alias="DB_PROVIDER")
    queue_provider: str = Field(default="memory", alias="QUEUE_PROVIDER")
    secrets_provider: str = Field(default="env", alias="SECRETS_PROVIDER")
    channel_provider: str = Field(default="webhook", alias="CHANNEL_PROVIDER")

    # =========================================================
    # GEMINI  (POC — free tier)
    # =========================================================
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_vision_model: str = Field(
        default="gemini-1.5-flash", alias="GEMINI_VISION_MODEL"
    )
    llm_default_temperature: float = Field(default=0.2, alias="LLM_DEFAULT_TEMPERATURE")
    llm_max_output_tokens: int = Field(default=1024, alias="LLM_MAX_OUTPUT_TOKENS")

    # =========================================================
    # SUPABASE  (POC — free tier)
    # =========================================================
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(
        default=None, alias="SUPABASE_SERVICE_ROLE_KEY"
    )

    # =========================================================
    # STORAGE  (POC: local disk)
    # =========================================================
    local_storage_base_path: str = Field(
        default="./data/uploads", alias="LOCAL_STORAGE_BASE_PATH"
    )

    # =========================================================
    # AWS — S3 STORAGE  (Production — P-004)
    # =========================================================
    s3_bucket: str | None = Field(default=None, alias="S3_BUCKET")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    s3_presign_expiry_seconds: int = Field(
        default=3600, alias="S3_PRESIGN_EXPIRY_SECONDS"
    )

    # =========================================================
    # CLAIM ROUTING THRESHOLDS
    # =========================================================
    lane1_max_compensation_usd: float = Field(
        default=100.0, alias="LANE1_MAX_COMPENSATION_USD"
    )
    fraud_phash_threshold: int = Field(default=10, alias="FRAUD_PHASH_THRESHOLD")
    claim_id_prefix: str = Field(default="CLM", alias="CLAIM_ID_PREFIX")
    imagehash_enabled: bool = Field(default=True, alias="IMAGEHASH_ENABLED")
    claim_frequency_window_days: int = Field(
        default=30, alias="CLAIM_FREQUENCY_WINDOW_DAYS"
    )
    max_claims_per_passenger: int = Field(default=3, alias="MAX_CLAIMS_PER_PASSENGER")


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton.

    Uses lru_cache so the .env file is read only once per process.
    Call get_settings.cache_clear() in tests to reset between cases.

    Returns:
        Settings: The application settings instance.
    """
    return Settings()