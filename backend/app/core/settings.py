from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="OpenCoWork Backend")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)

    @field_validator("debug", mode="before")
    @classmethod
    def coerce_debug_from_env(cls, value: object) -> bool | object:
        """Map env strings to bool; unknown strings (e.g. 'release') become False."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("true", "1", "yes", "on"):
                return True
            if normalized in ("false", "0", "no", "off", ""):
                return False
            return False
        return value

    log_level: str | None = Field(default=None, alias="LOG_LEVEL")
    log_sql: bool = Field(default=False, alias="LOG_SQL")
    uvicorn_access_log: bool = Field(default=False, alias="UVICORN_ACCESS_LOG")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    database_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/postgres"
    )
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)
    db_pool_timeout_seconds: int = Field(default=30)

    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    secret_key: str = Field(default="change-this-secret-key-in-production")
    internal_api_token: str = Field(
        default="change-this-token-in-production", alias="INTERNAL_API_TOKEN"
    )
    trusted_user_header_token: str = Field(
        default="",
        alias="TRUSTED_USER_HEADER_TOKEN",
        description="Optional shared secret for trusted proxies that set X-User-Id.",
    )
    allow_default_user: bool = Field(
        default=False,
        alias="ALLOW_DEFAULT_USER",
        description="Allow unauthenticated requests to use the single default user.",
    )
    bootstrap_on_startup: bool = Field(default=True, alias="BOOTSTRAP_ON_STARTUP")

    # External services
    executor_manager_url: str = Field(
        default="http://localhost:8001", alias="EXECUTOR_MANAGER_URL"
    )
    im_event_dispatch_enabled: bool = Field(
        default=False, alias="IM_EVENT_DISPATCH_ENABLED"
    )
    im_event_dispatch_interval_seconds: float = Field(
        default=0.5, alias="IM_EVENT_DISPATCH_INTERVAL_SECONDS"
    )
    im_event_dispatch_batch_size: int = Field(
        default=20, alias="IM_EVENT_DISPATCH_BATCH_SIZE"
    )
    im_event_dispatch_lease_seconds: int = Field(
        default=30, alias="IM_EVENT_DISPATCH_LEASE_SECONDS"
    )

    # Embedded IM integration
    backend_user_id: str = Field(default="default", alias="BACKEND_USER_ID")
    frontend_public_url: str = Field(
        default="http://localhost:3000", alias="FRONTEND_PUBLIC_URL"
    )
    frontend_default_language: str = Field(default="zh", alias="FRONTEND_DEFAULT_LANG")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret_token: str | None = Field(
        default=None, alias="TELEGRAM_WEBHOOK_SECRET_TOKEN"
    )

    dingtalk_enabled: bool = Field(default=True, alias="DINGTALK_ENABLED")
    dingtalk_webhook_token: str | None = Field(
        default=None, alias="DINGTALK_WEBHOOK_TOKEN"
    )
    dingtalk_stream_enabled: bool = Field(default=True, alias="DINGTALK_STREAM_ENABLED")
    dingtalk_stream_subscribe_events: bool = Field(
        default=False, alias="DINGTALK_STREAM_SUBSCRIBE_EVENTS"
    )
    dingtalk_client_id: str | None = Field(default=None, alias="DINGTALK_CLIENT_ID")
    dingtalk_client_secret: str | None = Field(
        default=None, alias="DINGTALK_CLIENT_SECRET"
    )
    dingtalk_robot_code: str | None = Field(default=None, alias="DINGTALK_ROBOT_CODE")
    dingtalk_open_base_url: str = Field(
        default="https://api.dingtalk.com",
        alias="DINGTALK_OPEN_BASE_URL",
    )
    dingtalk_webhook_url: str | None = Field(default=None, alias="DINGTALK_WEBHOOK_URL")

    feishu_enabled: bool = Field(default=False, alias="FEISHU_ENABLED")
    feishu_stream_enabled: bool = Field(default=True, alias="FEISHU_STREAM_ENABLED")
    feishu_app_id: str | None = Field(default=None, alias="FEISHU_APP_ID")
    feishu_app_secret: str | None = Field(default=None, alias="FEISHU_APP_SECRET")
    feishu_verification_token: str | None = Field(
        default=None, alias="FEISHU_VERIFICATION_TOKEN"
    )
    feishu_base_url: str = Field(
        default="https://open.feishu.cn",
        alias="FEISHU_BASE_URL",
    )
    feishu_bot_user_id: str | None = Field(default=None, alias="FEISHU_BOT_USER_ID")
    feishu_bot_open_id: str | None = Field(default=None, alias="FEISHU_BOT_OPEN_ID")
    feishu_bot_union_id: str | None = Field(default=None, alias="FEISHU_BOT_UNION_ID")
    feishu_bot_name: str | None = Field(default=None, alias="FEISHU_BOT_NAME")

    s3_endpoint: str | None = Field(default=None, alias="S3_ENDPOINT")
    s3_public_endpoint: str | None = Field(default=None, alias="S3_PUBLIC_ENDPOINT")
    s3_access_key: str | None = Field(default=None, alias="S3_ACCESS_KEY")
    s3_secret_key: str | None = Field(default=None, alias="S3_SECRET_KEY")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    s3_bucket: str | None = Field(default=None, alias="S3_BUCKET")
    s3_force_path_style: bool = Field(default=True, alias="S3_FORCE_PATH_STYLE")
    s3_presign_expires: int = Field(default=300, alias="S3_PRESIGN_EXPIRES")
    s3_connect_timeout_seconds: int = Field(
        default=5, alias="S3_CONNECT_TIMEOUT_SECONDS"
    )
    s3_read_timeout_seconds: int = Field(default=60, alias="S3_READ_TIMEOUT_SECONDS")
    s3_max_attempts: int = Field(default=3, alias="S3_MAX_ATTEMPTS")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_auth_token: str = Field(default="", alias="ANTHROPIC_AUTH_TOKEN")
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com", alias="ANTHROPIC_BASE_URL"
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    openai_audio_transcription_model: str = Field(
        default="whisper-1", alias="OPENAI_AUDIO_TRANSCRIPTION_MODEL"
    )
    siliconflow_api_key: str | None = Field(default=None, alias="SILICONFLOW_API_KEY")
    siliconflow_base_url: str = Field(
        default="https://api.siliconflow.cn/v1", alias="SILICONFLOW_BASE_URL"
    )
    siliconflow_rerank_model: str = Field(
        default="BAAI/bge-reranker-v2-m3", alias="SILICONFLOW_RERANK_MODEL"
    )
    siliconflow_timeout_seconds: float = Field(
        default=15.0, alias="SILICONFLOW_TIMEOUT_SECONDS"
    )
    default_model: str = Field(
        default="claude-sonnet-4-20250514", alias="DEFAULT_MODEL"
    )
    model_list: list[str] = Field(default_factory=list, alias="MODEL_LIST")
    max_upload_size_mb: int = Field(default=100, alias="MAX_UPLOAD_SIZE_MB")
    max_audio_upload_size_mb: int = Field(default=25, alias="MAX_AUDIO_UPLOAD_SIZE_MB")
    skillsmp_base_url: str = Field(
        default="https://skillsmp.com", alias="SKILLSMP_BASE_URL"
    )
    skillsmp_api_key: str = Field(default="", alias="SKILLSMP_API_KEY")
    skillsmp_timeout_seconds: float = Field(
        default=10.0, alias="SKILLSMP_TIMEOUT_SECONDS"
    )

    # OnlyOffice Document Server
    office_jwt_secret: str = Field(default="", alias="OFFICE_JWT_SECRET")
    office_document_server_url: str = Field(
        default="", alias="OFFICE_DOCUMENT_SERVER_URL"
    )
    office_file_size_limit_mb: int = Field(
        default=50, alias="OFFICE_FILE_SIZE_LIMIT_MB"
    )
    office_presign_expires_seconds: int = Field(
        default=600,
        alias="OFFICE_PRESIGN_EXPIRES_SECONDS",
        description="Presigned GET TTL for OnlyOffice Document Server fetches (seconds).",
    )
    office_callback_base_url: str = Field(
        default="http://localhost:8000/api/v1",
        alias="OFFICE_CALLBACK_BASE_URL",
        description="Public backend API v1 base URL used by OnlyOffice callbacks.",
    )
    office_callback_jwt_required: bool = Field(
        default=True,
        alias="OFFICE_CALLBACK_JWT_REQUIRED",
        description="Require OnlyOffice callback JWT validation.",
    )
    office_edit_session_ttl_seconds: int = Field(
        default=1800,
        alias="OFFICE_EDIT_SESSION_TTL_SECONDS",
        description="TTL for short-lived OnlyOffice edit sessions.",
        gt=0,
    )
    office_save_request_ttl_seconds: int = Field(
        default=3600,
        alias="OFFICE_SAVE_REQUEST_TTL_SECONDS",
        description="TTL for short-lived OnlyOffice save request status records.",
        gt=0,
    )
    office_editing_cleanup_interval_seconds: float = Field(
        default=60.0,
        alias="OFFICE_EDITING_CLEANUP_INTERVAL_SECONDS",
        description="Interval for evicting expired Office editing state.",
        gt=0,
    )
    office_editing_state_file: str = Field(
        default="",
        alias="OFFICE_EDITING_STATE_FILE",
        description="Optional JSON file path used to persist short-lived Office editing state.",
    )

    # Memory (Mem0)
    mem0_enabled: bool = Field(default=False, alias="MEM0_ENABLED")
    mem0_vector_provider: str = Field(default="pgvector", alias="MEM0_VECTOR_PROVIDER")
    mem0_postgres_host: str = Field(default="postgres", alias="MEM0_POSTGRES_HOST")
    mem0_postgres_port: int = Field(default=5432, alias="MEM0_POSTGRES_PORT")
    mem0_postgres_db: str = Field(default="postgres", alias="MEM0_POSTGRES_DB")
    mem0_postgres_user: str = Field(default="postgres", alias="MEM0_POSTGRES_USER")
    mem0_postgres_password: str = Field(
        default="postgres", alias="MEM0_POSTGRES_PASSWORD"
    )
    mem0_postgres_collection_name: str = Field(
        default="memories", alias="MEM0_POSTGRES_COLLECTION_NAME"
    )
    mem0_graph_provider: str = Field(default="neo4j", alias="MEM0_GRAPH_PROVIDER")
    mem0_neo4j_uri: str = Field(default="bolt://neo4j:7687", alias="MEM0_NEO4J_URI")
    mem0_neo4j_username: str = Field(default="neo4j", alias="MEM0_NEO4J_USERNAME")
    mem0_neo4j_password: str = Field(default="mem0graph", alias="MEM0_NEO4J_PASSWORD")
    mem0_memgraph_uri: str = Field(
        default="bolt://localhost:7687", alias="MEM0_MEMGRAPH_URI"
    )
    mem0_memgraph_username: str = Field(
        default="memgraph", alias="MEM0_MEMGRAPH_USERNAME"
    )
    mem0_memgraph_password: str = Field(
        default="mem0graph", alias="MEM0_MEMGRAPH_PASSWORD"
    )
    mem0_llm_model: str = Field(
        default="gpt-4.1-nano-2025-04-14", alias="MEM0_LLM_MODEL"
    )
    mem0_embedder_model: str = Field(
        default="text-embedding-3-small", alias="MEM0_EMBEDDER_MODEL"
    )
    mem0_embedding_dims: int = Field(default=1024, alias="MEM0_EMBEDDING_DIMS")
    mem0_history_db_path: str = Field(
        default="/tmp/poco/memory/history.db", alias="MEM0_HISTORY_DB_PATH"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
