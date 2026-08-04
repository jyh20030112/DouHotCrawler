from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, Path as ApiPath, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import ApiSettings
from .errors import ApiError
from .models import (
    AnalyzeTaskRequest,
    CrawlTaskRequest,
    ErrorResponse,
    HealthResponse,
    KeywordResponse,
    PipelineTaskRequest,
    TaskAcceptedResponse,
    TaskResponse,
    UploadTaskRequest,
)
from .service import ApiTaskService


API_DESCRIPTION = """
DouHotCrawler 的异步任务 API，接口前缀统一为 `/api/v1`。

### 调用方式

1. 调用创建任务接口，保存响应中的 `task_id`。
2. 轮询 `GET /api/v1/tasks/{task_id}` 获取进度和最终结果。
3. 需要中断时调用 `pause`；状态变为 `paused` 后可调用 `resume`。

### 执行与数据规则

- 所有 crawl、analyze、upload 和 pipeline 任务进入同一个持久化 FIFO 队列，严格串行执行。
- pipeline 按关键词依次执行 **爬取 → 口播提取 → 每 20 条发送**，不会并发处理关键词。
- 单关键词默认最多 500 条；`keywords=null` 时从热点接口获取默认 30 个关键词。
- Cookie 在每个阶段从外部配置接口读取，只保存在内存，不写入 SQLite、Excel 或日志。
- Excel 使用跨进程文件锁与原子替换保存。
- Excel 和任务日志保留 3 天，终态 SQLite 元数据保留 7 天；活动及暂停任务不会清理。

### 任务状态

`queued → running → succeeded | succeeded_with_warnings | failed`

暂停过程为 `running → pausing → paused → queued → running`。`upload_failure` 会自动暂停，恢复后重发未成功批次。

### 身份认证

当前 API 不要求认证，默认仅监听 `127.0.0.1`。
"""

OPENAPI_TAGS = [
    {"name": "系统", "description": "服务健康状态和运行依赖。"},
    {"name": "关键词", "description": "从外部热点服务读取爬虫关键词。"},
    {"name": "任务创建", "description": "创建异步爬取、口播或完整流水线任务。"},
    {"name": "任务控制", "description": "查询进度，以及安全暂停和恢复任务。"},
]

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "请求语义错误"},
    404: {"model": ErrorResponse, "description": "任务或结果文件不存在"},
    409: {"model": ErrorResponse, "description": "任务状态或 Excel 文件锁冲突"},
    422: {"model": ErrorResponse, "description": "Pydantic 参数校验失败"},
    502: {"model": ErrorResponse, "description": "外部服务请求或响应异常"},
    503: {"model": ErrorResponse, "description": "服务依赖暂不可用"},
    500: {"model": ErrorResponse, "description": "未预期的服务器内部错误"},
}

TaskId = Annotated[
    str,
    ApiPath(
        min_length=36,
        max_length=36,
        description="创建任务接口返回的 UUID。",
        examples=["42118d44-6334-4a0c-a9a5-9a5096ab2962"],
    ),
]


def error_response(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def create_app(
    settings: ApiSettings | None = None,
    service: ApiTaskService | None = None,
) -> FastAPI:
    settings = settings or ApiSettings()
    task_service = service or ApiTaskService(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.task_service = task_service
        await task_service.start()
        try:
            yield
        finally:
            await task_service.close()

    app = FastAPI(
        title="DouHot Crawler API",
        summary="热点宝爬取、口播提取和榜单发送任务服务",
        description=API_DESCRIPTION,
        version="1.0.0",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.state.task_service = task_service

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {key: value for key, value in item.items() if key != "ctx"}
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_response("VALIDATION_ERROR", "请求参数校验失败", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response("HTTP_ERROR", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_response("INTERNAL_ERROR", "服务器内部错误"),
        )

    @app.get(
        "/api/v1/health",
        response_model=HealthResponse,
        tags=["系统"],
        summary="检查 API 运行状态",
        description=(
            "检查 FIFO worker、SQLite 和浏览器是否可用。该接口不会调用外部 Cookie 服务，"
            "也不会返回完整外部 URL 或任何 Cookie。"
        ),
        responses=ERROR_RESPONSES,
    )
    async def health() -> dict[str, Any]:
        return task_service.health()

    @app.get(
        "/api/v1/keywords",
        response_model=KeywordResponse,
        tags=["关键词"],
        summary="获取热点关键词",
        description=(
            "调用配置的热点接口，提取 `data.records[*].title`，去除空值和重复值后按原顺序"
            "返回。默认最多返回 `DOUHOT_HOTSPOT_SIZE=30` 个关键词。"
        ),
        responses=ERROR_RESPONSES,
    )
    async def keywords() -> dict[str, list[str]]:
        return {"key_word": await task_service.keywords()}

    @app.post(
        "/api/v1/tasks/crawl",
        response_model=TaskAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["任务创建"],
        summary="创建单关键词爬取任务",
        description=(
            "任务进入全局 FIFO 队列并立即返回 task_id。执行时实时获取 type=0 的 DouHot "
            "Cookie，在无持久化 Profile 的临时浏览器上下文中爬取；结果写入该任务自己的 "
            "`tasks/{task_id}/result.xlsx`。不传 limit 时最多采集 500 条。"
        ),
        responses=ERROR_RESPONSES,
    )
    async def create_crawl(request: CrawlTaskRequest) -> dict[str, Any]:
        task = task_service.create_crawl(request)
        return {"task_id": task["task_id"], "status": task["status"], "created": True}

    @app.post(
        "/api/v1/tasks/analyze",
        response_model=TaskAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["任务创建"],
        summary="创建口播提取任务",
        description=(
            "为一个已经成功的 crawl 任务补充视频口播。执行时实时获取 type=1 的 Douyin "
            "Cookie，并更新原爬取任务的 Excel。crawl_task_id 不存在、未成功或文件正被占用时"
            "分别返回 404/409。单条提取失败会继续处理后续视频并记录 warning。"
        ),
        responses=ERROR_RESPONSES,
    )
    async def create_analyze(request: AnalyzeTaskRequest) -> dict[str, Any]:
        task = task_service.create_analyze(request)
        return {"task_id": task["task_id"], "status": task["status"], "created": True}

    @app.post(
        "/api/v1/tasks/pipeline",
        response_model=TaskAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["任务创建"],
        summary="创建完整流水线任务",
        description=(
            "按关键词严格串行执行爬取、口播提取和榜单发送。keywords 为 null 时自动获取热点"
            "关键词；上传时跳过缺少视频名称、URL、博主或口播的行，每批固定 20 条。若已有 "
            "queued/running/pausing/paused 流水线，则返回原 task_id 且 created=false。"
        ),
        responses=ERROR_RESPONSES,
    )
    async def create_pipeline(request: PipelineTaskRequest) -> dict[str, Any]:
        task, created = task_service.create_pipeline(request)
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "created": created,
        }

    @app.post(
        "/api/v1/tasks/upload",
        response_model=TaskAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["任务创建"],
        summary="上传现有 Excel 的全部合格数据",
        description=(
            "通过 source_task_id 找到 crawl、analyze 或 pipeline 任务对应的现有 Excel，默认遍历"
            "全部 Sheet 并发送到榜单数据库。缺少视频名称、视频 URL、博主名称或视频口播的行"
            "会跳过；其余记录每 20 条一批发送。发送进度写入 SQLite，上传失败时任务自动暂停，"
            "调用 resume 后只重发当前上传任务中尚未成功的记录。"
        ),
        responses=ERROR_RESPONSES,
    )
    async def create_upload(request: UploadTaskRequest) -> dict[str, Any]:
        task = task_service.create_upload(request)
        return {"task_id": task["task_id"], "status": task["status"], "created": True}

    @app.post(
        "/api/v1/tasks/{task_id}/pause",
        response_model=TaskResponse,
        tags=["任务控制"],
        summary="安全暂停任务",
        description=(
            "queued 任务会立即变为 paused；running 任务先变为 pausing，并在当前视频、口播请求"
            "或上传批次完成后变为 paused。终态任务不能暂停。重复暂停 paused 任务是幂等的。"
        ),
        responses=ERROR_RESPONSES,
    )
    async def pause(task_id: TaskId) -> dict[str, Any]:
        return task_service.pause(task_id)

    @app.post(
        "/api/v1/tasks/{task_id}/resume",
        response_model=TaskResponse,
        tags=["任务控制"],
        summary="恢复暂停任务",
        description=(
            "仅 paused 任务可恢复。恢复后任务回到 queued，并从 Excel、关键词检查点和发送记录"
            "继续；Cookie 会重新从外部配置接口获取。"
        ),
        responses=ERROR_RESPONSES,
    )
    async def resume(task_id: TaskId) -> dict[str, Any]:
        return task_service.resume(task_id)

    @app.get(
        "/api/v1/tasks/{task_id}",
        response_model=TaskResponse,
        tags=["任务控制"],
        summary="查询任务状态与进度",
        description=(
            "返回任务类型、状态、当前阶段、动态进度、告警数、错误和结果 Excel 元数据。"
            "建议调用方轮询该接口，直到状态进入 succeeded、succeeded_with_warnings 或 failed。"
        ),
        responses=ERROR_RESPONSES,
    )
    async def task_status(task_id: TaskId) -> dict[str, Any]:
        return task_service.status(task_id)

    return app


def main() -> None:
    settings = ApiSettings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
    )


if __name__ == "__main__":
    main()
