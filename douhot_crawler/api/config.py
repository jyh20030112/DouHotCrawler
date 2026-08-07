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
    industry_api_url: AnyHttpUrl = Field(
        validation_alias="DOUHOT_INDUSTRY_API_URL"
    )
    cookie_api_url: AnyHttpUrl = Field(validation_alias="DOUHOT_COOKIE_API_URL")
    ranking_api_url: AnyHttpUrl = Field(
        validation_alias="DOUHOT_RANKING_API_URL"
    )
    industry_ranking_api_url: AnyHttpUrl = Field(
        validation_alias="DOUHOT_INDUSTRY_RANKING_API_URL"
    )
    extract_api_url: AnyHttpUrl = Field(validation_alias="EXTRACT_API_URL")
    hotspot_open_id: str = Field(
        min_length=1, validation_alias="DOUHOT_HOTSPOT_OPEN_ID"
    )
    hotspot_size: Annotated[int, Field(ge=1, le=30)] = Field(
        default=30, validation_alias="DOUHOT_HOTSPOT_SIZE"
    )
    industry_size: Annotated[int, Field(ge=1, le=30)] = Field(
        default=30, validation_alias="DOUHOT_INDUSTRY_SIZE"
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
    daily_enabled: bool = Field(
        default=True,
        validation_alias="DOUHOT_DAILY_ENABLED",
    )
    daily_time: str = Field(
        default="03:00",
        validation_alias="DOUHOT_DAILY_TIME",
    )

    connect_timeout_seconds: Annotated[float, Field(gt=0)] = 10.0
    read_timeout_seconds: Annotated[float, Field(gt=0)] = 90.0
    artifact_retention_days: Annotated[int, Field(ge=1)] = 3
    metadata_retention_days: Annotated[int, Field(ge=1)] = 7
    max_videos_per_keyword: Annotated[int, Field(ge=1, le=500)] = Field(
        default=3,
        validation_alias="DOUHOT_MAX_VIDEOS_PER_KEYWORD",
    )
    max_candidates_per_keyword: Annotated[int, Field(ge=1, le=500)] = Field(
        default=15,
        validation_alias="DOUHOT_MAX_CANDIDATES_PER_KEYWORD",
    )
    upload_batch_size: Literal[20] = 20

    @field_validator("data_root", mode="after")
    @classmethod
    def resolve_data_root(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("daily_time")
    @classmethod
    def validate_daily_time(cls, value: str) -> str:
        parts = value.strip().split(":")
        if (
            len(parts) != 2
            or not all(len(part) == 2 and part.isdigit() for part in parts)
        ):
            raise ValueError("DOUHOT_DAILY_TIME 必须使用 HH:MM 格式")
        hour, minute = (int(part) for part in parts)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("DOUHOT_DAILY_TIME 必须是有效的 24 小时时间")
        return f"{hour:02d}:{minute:02d}"

    @property
    def daily_hour_minute(self) -> tuple[int, int]:
        hour, minute = self.daily_time.split(":")
        return int(hour), int(minute)

    @property
    def is_server_platform(self) -> bool:
        return sys.platform != "win32"

    def external_url(self, name: str) -> str:
        return str(getattr(self, name)).rstrip("/")
