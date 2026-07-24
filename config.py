from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Hórus Connective Licitações"
    app_version: str = "0.17.2-desktop-beta"
    environment: str = "development"
    desktop_mode: bool = False
    database_url: str = "postgresql+psycopg://editais:editais@db:5432/editais"
    data_dir: Path = Path("./data")

    secret_key: str = "change-me-in-production"
    admin_username: str = "admin"
    admin_password: str = "horus123"
    admin_display_name: str = "Henrique"
    admin_role: str = "Diretor Executivo"
    auth_cookie_name: str = "horus_session"
    auth_cookie_secure: bool = False
    session_max_age_hours: int = 12
    trusted_hosts: str = "*"

    openai_api_key: str = ""
    ai_mode: str = "auto"
    openai_chat_model: str = "gpt-5-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    openai_max_output_tokens: int = 1200

    pncp_consulta_base_url: str = "https://pncp.gov.br/api/consulta"
    pncp_files_base_url: str = "https://pncp.gov.br/pncp-api"
    pncp_timeout_seconds: float = 60.0
    pncp_default_modalities: str = "6,4,8"
    pncp_max_date_range_days: int = 0
    pncp_api_batch_days: int = 30
    pncp_progress_commit_seconds: float = 1.0
    pncp_max_retries: int = 5
    pncp_retry_base_delay_seconds: float = 5.0
    pncp_retry_max_delay_seconds: float = 40.0
    pncp_request_delay_seconds: float = 0.8

    max_upload_mb: int = 30
    max_document_mb: int = 40
    max_zip_uncompressed_mb: int = 80
    max_zip_files: int = 50

    chunk_size_chars: int = 1400
    chunk_overlap_chars: int = 220
    rag_top_k: int = 10
    rag_max_context_chars: int = 26000
    max_chunks_per_document: int = 600

    scheduler_enabled: bool = False
    scheduler_hour: int = 6
    scheduler_minute: int = 0
    scheduler_timezone: str = "America/Sao_Paulo"
    scheduler_lookback_days: int = 1
    scheduler_max_pages: int = 5
    scheduler_download_documents: bool = True

    cors_origins: str = "http://localhost:8000"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> str:
        url = str(value)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def modality_ids(self) -> list[int]:
        return [int(value.strip()) for value in self.pncp_default_modalities.split(",") if value.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [value.strip() for value in self.trusted_hosts.split(",") if value.strip()] or ["*"]

    @property
    def session_max_age_seconds(self) -> int:
        return self.session_max_age_hours * 60 * 60

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_document_bytes(self) -> int:
        return self.max_document_mb * 1024 * 1024

    @property
    def max_zip_uncompressed_bytes(self) -> int:
        return self.max_zip_uncompressed_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
