from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import ApiSettings
from .errors import ApiError
from .models import (
    AnalyzeTaskRequest,
    CrawlTaskRequest,
    HealthResponse,
    KeywordResponse,
    PipelineTaskRequest,
    TaskAcceptedResponse,
    TaskResponse,
)
from .service import ApiTaskService


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

    app = FastAPI(title="DouHot Crawler API", version="1.0.0", lifespan=lifespan)
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

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> dict[str, Any]:
        return task_service.health()

    @app.get("/api/v1/keywords", response_model=KeywordResponse)
    async def keywords() -> dict[str, list[str]]:
        return {"key_word": await task_service.keywords()}

    @app.post(
        "/api/v1/tasks/crawl",
        response_model=TaskAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_crawl(request: CrawlTaskRequest) -> dict[str, Any]:
        task = task_service.create_crawl(request)
        return {"task_id": task["task_id"], "status": task["status"], "created": True}

    @app.post(
        "/api/v1/tasks/analyze",
        response_model=TaskAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_analyze(request: AnalyzeTaskRequest) -> dict[str, Any]:
        task = task_service.create_analyze(request)
        return {"task_id": task["task_id"], "status": task["status"], "created": True}

    @app.post(
        "/api/v1/tasks/pipeline",
        response_model=TaskAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_pipeline(request: PipelineTaskRequest) -> dict[str, Any]:
        task, created = task_service.create_pipeline(request)
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "created": created,
        }

    @app.post("/api/v1/tasks/{task_id}/pause", response_model=TaskResponse)
    async def pause(task_id: str) -> dict[str, Any]:
        return task_service.pause(task_id)

    @app.post("/api/v1/tasks/{task_id}/resume", response_model=TaskResponse)
    async def resume(task_id: str) -> dict[str, Any]:
        return task_service.resume(task_id)

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskResponse)
    async def task_status(task_id: str) -> dict[str, Any]:
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
