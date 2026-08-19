from __future__ import annotations

from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Fulgencio Voice Agent"
    log_level: str = "INFO"

    model_name: str = "gpt-realtime-1.5"
    realtime_voice: str = "shimmer"
    transcription_model: str = "whisper-1"
    litellm_proxy_http_url: str = "http://localhost:4000"
    litellm_proxy_ws_url: str = "ws://localhost:4000"
    litellm_proxy_api_key: str = ""
    litellm_master_key: str = ""

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-01-preview"

    firebase_database_url: str = ""
    firebase_service_account_json: str = ""

    azure_sql_connection_string: str = ""
    azure_sql_connect_timeout_seconds: int = Field(default=60, ge=1, le=300)
    azure_sql_connect_retry_attempts: int = Field(default=5, ge=1, le=10)
    azure_sql_connect_retry_base_seconds: float = Field(default=1.0, ge=0.0, le=30.0)
    azure_sql_connect_max_total_seconds: float = Field(default=45.0, ge=1.0, le=300.0)

    ws_basic_username: str = ""
    ws_basic_password: str = ""
    max_audio_chunk_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)
    drawing_start_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    drawing_complete_timeout_seconds: float = Field(default=300.0, ge=30.0, le=1_800.0)

    @model_validator(mode="after")
    def use_master_key_for_proxy(self) -> Self:
        if not self.litellm_proxy_api_key and self.litellm_master_key:
            self.litellm_proxy_api_key = self.litellm_master_key
        self.litellm_proxy_http_url = self.litellm_proxy_http_url.rstrip("/")
        self.litellm_proxy_ws_url = self.litellm_proxy_ws_url.rstrip("/")
        return self

    def runtime_errors(self) -> list[str]:
        required = {
            "LITELLM_PROXY_API_KEY o LITELLM_MASTER_KEY": self.litellm_proxy_api_key,
            "FIREBASE_DATABASE_URL": self.firebase_database_url,
            "FIREBASE_SERVICE_ACCOUNT_JSON": self.firebase_service_account_json,
            "AZURE_SQL_CONNECTION_STRING": self.azure_sql_connection_string,
            "WS_BASIC_USERNAME": self.ws_basic_username,
            "WS_BASIC_PASSWORD": self.ws_basic_password,
        }
        return [name for name, value in required.items() if not str(value).strip()]

    def assert_runtime_ready(self) -> None:
        errors = self.runtime_errors()
        if errors:
            raise RuntimeError("Faltan variables de entorno: " + ", ".join(errors))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
