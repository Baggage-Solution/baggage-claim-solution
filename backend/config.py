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
    # AWS — SECRETS MANAGER  (Production — P-005)
    # =========================================================
    # Reuses aws_region (declared further below) — no separate
    # secrets_manager_region field. Only consulted when
    # SECRETS_PROVIDER=aws_sm; harmless placeholder otherwise.
    secrets_manager_name: str = Field(
        default="baggage-claim/local", alias="SECRETS_MANAGER_NAME"
    )

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
    # AWS — BEDROCK LLM/VISION/OCR  (Production — P-003)
    # =========================================================
    # Reuses aws_region above rather than declaring a separate
    # bedrock_region — one AWS region setting shared across all AWS
    # providers (S3, Bedrock, and future SQS/Secrets Manager).
    #
    # Default model: Claude Haiku 4.5 (anthropic.claude-haiku-4-5-20251001-v1:0)
    # — chosen over Sonnet 4 for cost; Haiku 4.5 supports vision, so the same
    # model ID is used for LLM, vision, and OCR. To use cross-region inference
    # (higher throughput within a geography), prefix with a region code, e.g.
    # "us.anthropic.claude-haiku-4-5-20251001-v1:0".
    bedrock_llm_model: str = Field(
        default="anthropic.claude-haiku-4-5-20251001-v1:0", alias="BEDROCK_LLM_MODEL"
    )
    bedrock_vision_model: str = Field(
        default="anthropic.claude-haiku-4-5-20251001-v1:0",
        alias="BEDROCK_VISION_MODEL",
    )
    bedrock_ocr_model: str = Field(
        default="anthropic.claude-haiku-4-5-20251001-v1:0", alias="BEDROCK_OCR_MODEL"
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


# Settings field name -> Secrets Manager JSON key name. Only fields that are
# genuinely secret (credentials) are listed here — provider switches, model
# IDs, and thresholds always come from env/.env regardless of SECRETS_PROVIDER,
# since they are configuration, not secrets, and belong in version-controlled
# .env.example rather than a vaulted blob.
#
# This map is intentionally small today (matches the task note: "Bedrock +
# Supabase + Meta creds all live in ONE secret JSON"). Bedrock itself needs
# no secret (AWS credentials come from the IAM role, not from this app), so
# only the Supabase trio is mapped for now. Meta WhatsApp credentials will be
# added here when P-021 introduces them — same pattern, just more entries.
_SECRET_FIELD_MAP = {
    "supabase_url": "SUPABASE_URL",
    "supabase_anon_key": "SUPABASE_ANON_KEY",
    "supabase_service_role_key": "SUPABASE_SERVICE_ROLE_KEY",
}


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton.

    Uses lru_cache so the .env file (and, when applicable, Secrets Manager)
    is read only once per process. Call get_settings.cache_clear() in tests
    to reset between cases.

    When SECRETS_PROVIDER=aws_sm, this function fetches the configured
    Secrets Manager secret and re-validates Settings with any matching
    fields overridden by the secret's values — fields present in
    _SECRET_FIELD_MAP but absent from this env's .env file are populated
    from the vault instead. Fields not present in the secret JSON keep
    their .env/default value, so a partially-populated secret degrades
    gracefully rather than wiping out unrelated settings.

    This intentionally happens AFTER the first Settings() construction so
    that secrets_manager_name and secrets_provider themselves (needed to
    know *which* secret to fetch) are always read from plain env vars,
    never from the secret itself — avoiding the chicken-and-egg problem of
    needing a secret to find out which secret to load.

    Returns:
        Settings: The application settings instance, with AWS-sourced
        fields populated from Secrets Manager when configured.
    """
    settings = Settings()

    if settings.secrets_provider != "aws_sm":
        return settings

    from backend.secrets_provider.aws_secrets import AWSSecretsManagerProvider

    provider = AWSSecretsManagerProvider(
        secret_name=settings.secrets_manager_name,
        region=settings.aws_region,
    )

    overrides: dict[str, str] = {}
    for field_name, secret_key in _SECRET_FIELD_MAP.items():
        try:
            overrides[field_name] = provider.get(secret_key)
        except KeyError:
            # Key absent from this particular secret — keep whatever
            # value Settings() already has (env/.env/default). Logged
            # inside AWSSecretsManagerProvider.get() already; no need
            # to log twice here.
            continue

    if overrides:
        settings = settings.model_copy(update=overrides)

    return settings