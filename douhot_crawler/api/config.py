from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from douhot_crawler.core.config import _data_dir


class ApiSettings(BaseSettings):
    """Validated API and external-service configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    hotspot_api_url: AnyHttpUrl = Field(
        validation_alias="DOUHOT_HOTSPOT_API_URL"
    )
    cookie_api_url: AnyHttpUrl = Field(validation_alias="DOUHOT_COOKIE_API_URL")
    ranking_api_url: AnyHttpUrl = Field(
        validation_alias="DOUHOT_RANKING_API_URL"
    )
    extract_api_url: AnyHttpUrl = Field(validation_alias="EXTRACT_API_URL")
    hotspot_open_id: str = Field(
        min_length=1, validation_alias="DOUHOT_HOTSPOT_OPEN_ID"
    )
    hotspot_size: Annotated[int, Field(ge=1, le=30)] = Field(
        default=30, validation_alias="DOUHOT_HOTSPOT_SIZE"
    )

    data_root: Path = Field(
        default_factory=lambda: _data_dir() / "api",
        validation_alias="DOUHOT_API_DATA_ROOT",
    )
    host: str = Field(default="127.0.0.1", validation_alias="DOUHOT_API_HOST")
    port: Annotated[int, Field(ge=1, le=65535)] = Field(
        default=8000, validation_alias="DOUHOT_API_PORT"
    )
    workers: Annotated[int, Field(ge=1, le=1)] = Field(
        default=1, validation_alias="DOUHOT_API_WORKERS"
    )
    daily_api_url: AnyHttpUrl = Field(
        default="http://127.0.0.1:8000",
        validation_alias="DOUHOT_DAILY_API_URL",
    )

    connect_timeout_seconds: Annotated[float, Field(gt=0)] = 10.0
    read_timeout_seconds: Annotated[float, Field(gt=0)] = 90.0
    artifact_retention_days: Annotated[int, Field(ge=1)] = 3
    metadata_retention_days: Annotated[int, Field(ge=1)] = 7
    max_videos_per_keyword: Annotated[int, Field(ge=1, le=500)] = Field(
        default=3,
        validation_alias="DOUHOT_MAX_VIDEOS_PER_KEYWORD",
    )
    upload_batch_size: Literal[20] = 20

    @field_validator("data_root", mode="after")
    @classmethod
    def resolve_data_root(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @property
    def is_server_platform(self) -> bool:
        return sys.platform != "win32"

    def external_url(self, name: str) -> str:
        return str(getattr(self, name)).rstrip("/")
