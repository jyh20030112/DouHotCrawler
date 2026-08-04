from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from douhot_crawler.core.config import (
    DEFAULT_DETAIL_DELAY,
    DEFAULT_RESULT_TYPE,
    DEFAULT_TIME_RANGE,
    RESULT_TYPE_CHOICES,
    TIME_RANGE_CHOICES,
)


class TaskKind(StrEnum):
    CRAWL = "crawl"
    ANALYZE = "analyze"
    PIPELINE = "pipeline"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    SUCCEEDED_WITH_WARNINGS = "succeeded_with_warnings"
    FAILED = "failed"


TERMINAL_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.SUCCEEDED_WITH_WARNINGS,
    TaskStatus.FAILED,
}
ACTIVE_PIPELINE_STATUSES = {
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.PAUSING,
    TaskStatus.PAUSED,
}


class CrawlTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(min_length=1, max_length=200)
    result_type: str = DEFAULT_RESULT_TYPE
    time_range: str = DEFAULT_TIME_RANGE
    input_timeout: Annotated[float, Field(gt=0, le=300)] = 30.0
    detail_delay: Annotated[float, Field(ge=0, le=60)] = DEFAULT_DETAIL_DELAY
    limit: Annotated[int, Field(ge=1, le=500)] | None = None

    @field_validator("keyword")
    @classmethod
    def clean_keyword(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("keyword 不能为空")
        return value

    @field_validator("result_type")
    @classmethod
    def validate_result_type(cls, value: str) -> str:
        if value not in RESULT_TYPE_CHOICES:
            raise ValueError(f"result_type 必须是：{', '.join(RESULT_TYPE_CHOICES)}")
        return value

    @field_validator("time_range")
    @classmethod
    def validate_time_range(cls, value: str) -> str:
        if value not in TIME_RANGE_CHOICES:
            raise ValueError(f"time_range 必须是：{', '.join(TIME_RANGE_CHOICES)}")
        return value


class AnalyzeTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crawl_task_id: str = Field(min_length=36, max_length=36)
    sheets: list[str] | None = None
    timeout: Annotated[float, Field(gt=0, le=600)] = 90.0
    delay: Annotated[float, Field(ge=0, le=60)] = 0.0
    limit: Annotated[int, Field(ge=1)] | None = None
    overwrite: bool = False

    @field_validator("sheets")
    @classmethod
    def clean_sheets(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not cleaned:
            raise ValueError("sheets 不能为空列表")
        return cleaned


class PipelineTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[str] | None = None
    result_type: str = DEFAULT_RESULT_TYPE
    time_range: str = DEFAULT_TIME_RANGE
    input_timeout: Annotated[float, Field(gt=0, le=300)] = 30.0
    detail_delay: Annotated[float, Field(ge=0, le=60)] = DEFAULT_DETAIL_DELAY
    limit_per_keyword: Annotated[int, Field(ge=1, le=500)] | None = None
    overwrite_transcript: bool = False

    @model_validator(mode="after")
    def validate_request(self) -> "PipelineTaskRequest":
        CrawlTaskRequest(
            keyword="validation",
            result_type=self.result_type,
            time_range=self.time_range,
            input_timeout=self.input_timeout,
            detail_delay=self.detail_delay,
            limit=self.limit_per_keyword,
        )
        if self.keywords is not None:
            cleaned = list(
                dict.fromkeys(item.strip() for item in self.keywords if item.strip())
            )
            if not cleaned:
                raise ValueError("keywords 不能为空列表")
            if len(cleaned) > 30:
                raise ValueError("keywords 最多允许 30 个")
            self.keywords = cleaned
        return self


class KeywordResponse(BaseModel):
    key_word: list[str]


class TaskAcceptedResponse(BaseModel):
    task_id: str
    status: TaskStatus
    created: bool = True


class ArtifactResponse(BaseModel):
    path: str
    row_count: int
    sha256: str


class TaskResponse(BaseModel):
    task_id: str
    kind: TaskKind
    status: TaskStatus
    phase: str | None = None
    params: dict[str, Any]
    progress: dict[str, Any]
    artifact: ArtifactResponse | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    warning_count: int = 0
    pause_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    worker_running: bool
    database_ok: bool
    browser_ok: bool
    external_urls_configured: bool
    scheduler_overlap: bool
