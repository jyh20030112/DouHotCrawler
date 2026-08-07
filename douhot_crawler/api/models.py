from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

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
    UPLOAD = "upload"
    PIPELINE = "pipeline"
    COLLECT = "collect"


class PipelineDataSource(StrEnum):
    HOTSPOT = "hotspot"
    INDUSTRY = "industry"
    ALL = "all"


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
    """创建单关键词热点宝爬取任务。"""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "keyword": "大健康",
                    "result_type": "低粉爆款",
                    "time_range": "近7天",
                    "input_timeout": 30,
                    "detail_delay": 1,
                    "limit": 5,
                }
            ]
        },
    )

    keyword: str = Field(
        min_length=1,
        max_length=200,
        description="用于热点宝搜索和 Excel Sheet 命名的关键词。",
        examples=["大健康"],
    )
    result_type: str = Field(
        default=DEFAULT_RESULT_TYPE,
        description=f"榜单类型：{'、'.join(RESULT_TYPE_CHOICES)}。",
        examples=["低粉爆款"],
    )
    time_range: str = Field(
        default=DEFAULT_TIME_RANGE,
        description=f"榜单时间范围：{'、'.join(TIME_RANGE_CHOICES)}。",
        examples=["近7天"],
    )
    input_timeout: Annotated[
        float,
        Field(gt=0, le=300, description="等待搜索输入框出现的最长秒数。"),
    ] = 30.0
    detail_delay: Annotated[
        float,
        Field(ge=0, le=60, description="采集两条视频详情之间的基础等待秒数。"),
    ] = DEFAULT_DETAIL_DELAY
    limit: Annotated[
        int | None,
        Field(
            ge=1,
            le=500,
            description=(
                "最多采集条数；null 时使用 DOUHOT_MAX_VIDEOS_PER_KEYWORD，默认 3。"
            ),
        ),
    ] = None

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
    """为一个已成功爬取任务的 Excel 补充视频口播和播放地址。"""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "crawl_task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
                    "sheets": ["大健康"],
                    "timeout": 90,
                    "delay": 0,
                    "limit": None,
                    "overwrite": False,
                }
            ]
        },
    )

    crawl_task_id: str = Field(
        min_length=36,
        max_length=36,
        description="已进入 succeeded 或 succeeded_with_warnings 状态的 crawl 任务 UUID。",
    )
    sheets: list[str] | None = Field(
        default=None,
        description="只处理这些 Sheet；不传或传 null 时处理工作簿全部 Sheet。",
        examples=[["大健康"]],
    )
    timeout: Annotated[
        float,
        Field(gt=0, le=600, description="单条口播提取请求的超时秒数。"),
    ] = 90.0
    delay: Annotated[
        float,
        Field(ge=0, le=60, description="两条口播提取请求之间的等待秒数。"),
    ] = 0.0
    limit: Annotated[
        int | None,
        Field(ge=1, description="本次最多处理的待提取记录数；null 表示全部。"),
    ] = None
    overwrite: bool = Field(
        default=False,
        description="是否重新提取并覆盖已经存在的视频口播和播放地址。",
    )

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
    """创建关键词获取、爬取、口播和发送的完整流水线。"""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "data_source": "all",
                    "keywords": None,
                    "result_type": "低粉爆款",
                    "time_range": "近7天",
                    "input_timeout": 30,
                    "detail_delay": 1,
                    "limit_per_keyword": None,
                    "candidate_limit_per_keyword": None,
                    "overwrite_transcript": False,
                },
                {
                    "data_source": "hotspot",
                    "keywords": ["大健康", "美容"],
                    "limit_per_keyword": 3,
                    "candidate_limit_per_keyword": 15,
                },
            ]
        },
    )

    data_source: PipelineDataSource = Field(
        default=PipelineDataSource.ALL,
        description=(
            "流水线数据源：hotspot 仅热点榜，industry 仅行业榜，all 先热点榜后行业榜。"
        ),
    )

    keywords: list[str] | None = Field(
        default=None,
        description=(
            "自定义关键词，最多 30 个并按原顺序去重；null 时从 data_source "
            "对应的外部接口获取。data_source=all 时必须为 null。"
        ),
        examples=[["大健康", "美容"]],
    )
    result_type: str = Field(
        default=DEFAULT_RESULT_TYPE,
        description=f"每个关键词使用的榜单类型：{'、'.join(RESULT_TYPE_CHOICES)}。",
    )
    time_range: str = Field(
        default=DEFAULT_TIME_RANGE,
        description=f"每个关键词使用的时间范围：{'、'.join(TIME_RANGE_CHOICES)}。",
    )
    input_timeout: Annotated[
        float,
        Field(gt=0, le=300, description="等待搜索输入框出现的最长秒数。"),
    ] = 30.0
    detail_delay: Annotated[
        float,
        Field(ge=0, le=60, description="采集两条视频详情之间的基础等待秒数。"),
    ] = DEFAULT_DETAIL_DELAY
    limit_per_keyword: Annotated[
        int | None,
        Field(
            ge=1,
            le=500,
            description=(
                "每个关键词最终需要的有效口播条数；null 时使用 "
                "DOUHOT_MAX_VIDEOS_PER_KEYWORD，默认 3。"
            ),
        ),
    ] = None
    candidate_limit_per_keyword: Annotated[
        int | None,
        Field(
            ge=1,
            le=500,
            description=(
                "每个关键词最多爬取的候选视频数；null 时使用 "
                "DOUHOT_MAX_CANDIDATES_PER_KEYWORD，默认 15。"
            ),
        ),
    ] = None
    overwrite_transcript: bool = Field(
        default=False,
        description="恢复流水线时是否覆盖工作簿中已有的视频口播和播放地址。",
    )

    @model_validator(mode="after")
    def validate_request(self) -> "PipelineTaskRequest":
        CrawlTaskRequest(
            keyword="validation",
            result_type=self.result_type,
            time_range=self.time_range,
            input_timeout=self.input_timeout,
            detail_delay=self.detail_delay,
            limit=self.candidate_limit_per_keyword,
        )
        if (
            self.limit_per_keyword is not None
            and self.candidate_limit_per_keyword is not None
            and self.candidate_limit_per_keyword < self.limit_per_keyword
        ):
            raise ValueError("候选视频上限不能小于有效口播目标")
        if self.data_source == PipelineDataSource.ALL and self.keywords is not None:
            raise ValueError("data_source=all 时不能传 keywords")
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


class CollectKeywordRequest(CrawlTaskRequest):
    """爬取并解析一个关键词，生成榜单视频请求数据。"""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "keyword": "大健康",
                    "result_type": "低粉爆款",
                    "time_range": "近7天",
                    "input_timeout": 30,
                    "detail_delay": 1,
                    "limit": 3,
                    "analyze_timeout": 90,
                    "analyze_delay": 0,
                    "callback_url": "https://example.com/hooks/douhot",
                },
            ]
        },
    )

    analyze_timeout: Annotated[
        float,
        Field(gt=0, le=600, description="单条口播提取请求的超时秒数。"),
    ] = 90.0
    analyze_delay: Annotated[
        float,
        Field(ge=0, le=60, description="两条口播提取请求之间的等待秒数。"),
    ] = 0.0
    callback_url: AnyHttpUrl | None = Field(
        default=None,
        description=(
            "异步结果回调地址。省略或传 null 时等待任务完成并直接返回最终数组。"
        ),
    )


class RankingViralVideoItem(BaseModel):
    """与 rankingViralVideo 请求数组元素完全一致的数据结构。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal[0] = Field(default=0, description="榜单数据类型，固定为 0。")
    keyword: str = Field(description="请求提供的原始关键词。")
    videoName: str = Field(description="视频名称。")
    videoUrl: str = Field(description="抖音视频分享链接。")
    authorName: str = Field(description="博主名称。")
    followerCount: int = Field(
        description="总粉丝数整数；源数据为空或无法解析时为 0。"
    )
    heatValue: str = Field(description="热度值，保留 Excel 展示格式。")
    newPlayCount: str = Field(description="新增播放量，保留 Excel 展示格式。")
    newLikeCount: str = Field(description="新增点赞量，保留 Excel 展示格式。")
    likeRate: str = Field(description="点赞率，保留 Excel 展示格式。")
    highPraiseComment: str = Field(description="高赞评论。")
    videoOral: str = Field(description="视频口播文本。")
    videoPlayUrl: str = Field(description="视频提取接口返回的直接播放地址。")


class UploadTaskRequest(BaseModel):
    """把一个任务现有 Excel 中的合格记录发送到榜单数据库。"""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "source_task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
                    "sheets": None,
                },
                {
                    "source_task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
                    "sheets": ["大健康", "美容"],
                },
            ]
        },
    )

    source_task_id: str = Field(
        min_length=36,
        max_length=36,
        description=(
            "包含目标 Excel 的 crawl、analyze 或 pipeline 任务 UUID；也允许使用已有文件的"
            " paused/failed 任务。"
        ),
    )
    sheets: list[str] | None = Field(
        default=None,
        description="只上传这些 Sheet；null 时上传 Excel 中全部 Sheet。",
        examples=[["大健康"]],
    )

    @field_validator("sheets")
    @classmethod
    def clean_sheets(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not cleaned:
            raise ValueError("sheets 不能为空列表")
        return cleaned


class KeywordResponse(BaseModel):
    key_word: list[str] = Field(
        description="去空、去重并保持外部热点接口原顺序的关键词列表。",
        examples=[["mj是什么网络梗", "mj是什么意思", "果园精选好物"]],
    )


class TaskAcceptedResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
                    "status": "queued",
                    "created": True,
                }
            ]
        }
    )

    task_id: str = Field(description="任务 UUID，用于查询、暂停和恢复。")
    status: TaskStatus = Field(description="创建后的任务状态，通常为 queued。")
    created: bool = Field(
        default=True,
        description="是否新建任务；流水线已有 active/paused 任务时为 false。",
    )


class ArtifactResponse(BaseModel):
    path: str = Field(description="相对于 DOUHOT_API_DATA_ROOT 的 Excel 路径。")
    row_count: int = Field(description="工作簿全部 Sheet 的数据行总数。")
    sha256: str = Field(description="结果 Excel 文件的 SHA-256。")


class TaskResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
                    "kind": "crawl",
                    "status": "running",
                    "phase": "crawl",
                    "params": {
                        "keyword": "大健康",
                        "result_type": "低粉爆款",
                        "time_range": "近7天",
                        "input_timeout": 30,
                        "detail_delay": 1,
                        "limit": 5,
                    },
                    "progress": {
                        "keyword": "大健康",
                        "page": 1,
                        "current": 3,
                        "added": 3,
                        "skipped": 0,
                    },
                    "artifact": None,
                    "result": None,
                    "error": None,
                    "warning_count": 0,
                    "pause_reason": None,
                    "created_at": "2026-08-04T10:46:19.118126Z",
                    "updated_at": "2026-08-04T10:46:20.847892Z",
                    "started_at": "2026-08-04T10:46:19.136795Z",
                    "finished_at": None,
                }
            ]
        }
    )

    task_id: str = Field(description="任务 UUID。")
    kind: TaskKind = Field(
        description="任务类型：crawl、analyze、upload、pipeline 或 collect。"
    )
    status: TaskStatus = Field(description="当前任务状态。")
    phase: str | None = Field(default=None, description="当前执行阶段。")
    params: dict[str, Any] = Field(description="创建任务时经过校验的请求参数。")
    progress: dict[str, Any] = Field(
        description="动态进度，包括关键词、Sheet、行号、成功/失败数和发送数。"
    )
    artifact: ArtifactResponse | None = Field(
        default=None, description="任务成功后生成或更新的 Excel 信息。"
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="终态任务的统计结果；collect 任务还包含 records 最终数组。",
    )
    error: str | None = Field(default=None, description="失败原因；非 failed 时为 null。")
    warning_count: int = Field(default=0, description="任务累计告警数。")
    pause_reason: str | None = Field(
        default=None,
        description="暂停原因：user、shutdown 或 upload_failure。",
    )
    created_at: datetime = Field(description="任务创建时间，UTC ISO 8601。")
    updated_at: datetime = Field(description="任务最后更新时间，UTC ISO 8601。")
    started_at: datetime | None = Field(default=None, description="首次开始时间。")
    finished_at: datetime | None = Field(default=None, description="进入终态的时间。")


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "worker_running": True,
                    "database_ok": True,
                    "browser_ok": True,
                    "external_urls_configured": True,
                    "scheduler_overlap": False,
                    "scheduler_enabled": True,
                    "scheduler_time": "03:00",
                    "scheduler_timezone": "Asia/Shanghai",
                    "scheduler_next_run_at": "2026-08-05T03:00:00+08:00",
                }
            ]
        }
    )

    status: str = Field(description="整体状态：ok 或 degraded。")
    worker_running: bool = Field(description="FIFO 后台 worker 是否运行。")
    database_ok: bool = Field(description="SQLite 是否可读写。")
    browser_ok: bool = Field(description="系统 Chrome/Edge 或 Playwright Chromium 是否可用。")
    external_urls_configured: bool = Field(description="外部接口地址是否已配置。")
    scheduler_overlap: bool = Field(description="是否已有 active/paused 流水线任务。")
    scheduler_enabled: bool = Field(description="FastAPI 内置每日调度是否启用。")
    scheduler_time: str = Field(description=".env 配置的每日触发时间，格式 HH:MM。")
    scheduler_timezone: str = Field(description="调度时区，固定为 Asia/Shanghai。")
    scheduler_next_run_at: datetime | None = Field(
        default=None,
        description="服务启动后计算出的下一次触发时间；关闭调度时为 null。",
    )


class ErrorDetail(BaseModel):
    code: str = Field(examples=["EXTERNAL_SERVICE_ERROR"])
    message: str = Field(examples=["Cookie 配置接口：请求处理异常，请稍后再试"])
    details: Any = Field(default=None, description="可选的参数校验等结构化详情。")


class ErrorResponse(BaseModel):
    error: ErrorDetail
