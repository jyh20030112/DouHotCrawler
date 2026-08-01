from __future__ import annotations

import os
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from .config import DEFAULT_DETAIL_DELAY, DEFAULT_RESULT_TYPE, DEFAULT_TIME_RANGE
from .job_service import JobManager

manager = JobManager()
mcp = FastMCP(
    "DouHotCrawler",
    instructions="按用户隔离执行热点宝扫码、爬取、口播提取和 Excel 导出。",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
)


@mcp.tool()
def douhot_health(user_id: str) -> dict[str, Any]:
    """检查当前用户的浏览器、热点宝登录态和口播提取配置。"""
    return manager.health(user_id)


@mcp.tool()
async def douhot_login_start(user_id: str) -> dict[str, Any]:
    """启动当前用户的热点宝网页扫码登录任务。"""
    return await manager.start_login(user_id)


@mcp.tool()
def douhot_login_status(user_id: str, job_id: str | None = None) -> dict[str, Any]:
    """查询扫码登录状态；waiting_login 时 download_url 是二维码图片。"""
    return manager.describe(user_id, job_id, kinds=("login",))


@mcp.tool()
async def douhot_login_cancel(
    user_id: str, job_id: str | None = None
) -> dict[str, Any]:
    """取消当前用户的扫码登录任务。"""
    return await manager.cancel(user_id, job_id, kinds=("login",))


@mcp.tool()
async def douhot_crawl_start(
    user_id: str,
    keyword: str,
    result_type: str = DEFAULT_RESULT_TYPE,
    time_range: str = DEFAULT_TIME_RANGE,
    input_timeout: float = 30.0,
    detail_delay: float = DEFAULT_DETAIL_DELAY,
) -> dict[str, Any]:
    """按关键词启动热点视频爬取任务，完成后生成独立 Excel。"""
    return await manager.start_crawl(
        user_id,
        keyword=keyword,
        result_type=result_type,
        time_range=time_range,
        input_timeout=input_timeout,
        detail_delay=detail_delay,
    )


@mcp.tool()
async def douhot_analyze_start(
    user_id: str,
    crawl_job_id: str | None = None,
    overwrite: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """对指定爬取任务的 Excel 启动批量口播提取。"""
    return await manager.start_analyze(
        user_id,
        crawl_job_id=crawl_job_id,
        overwrite=overwrite,
        limit=limit,
    )


@mcp.tool()
def douhot_job_status(user_id: str, job_id: str | None = None) -> dict[str, Any]:
    """查询当前用户的爬取或分析任务状态。"""
    return manager.describe(user_id, job_id, kinds=("crawl", "analyze"))


@mcp.tool()
async def douhot_job_cancel(
    user_id: str, job_id: str | None = None
) -> dict[str, Any]:
    """安全停止当前用户的爬取或分析任务。"""
    return await manager.cancel(user_id, job_id, kinds=("crawl", "analyze"))


@mcp.tool()
def douhot_list_videos(
    user_id: str,
    job_id: str | None = None,
    keyword: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    """按任务或关键词分页读取已有视频；关键词未命中时返回 found=false。"""
    return manager.list_videos(
        user_id, job_id, keyword=keyword, offset=offset, limit=limit
    )


@mcp.tool()
async def douhot_extract_transcript(user_id: str, share_link: str) -> dict[str, Any]:
    """提取一条已选视频的口播文本。"""
    return await manager.transcript(user_id, share_link)


@mcp.custom_route("/downloads/{job_id}", methods=["GET"])
async def download(request: Request):
    try:
        path, mime_type = manager.resolve_download(
            request.path_params["job_id"],
            request.query_params.get("owner", ""),
            request.query_params.get("expires", ""),
            request.query_params.get("signature", ""),
        )
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)
    return FileResponse(path, media_type=mime_type, filename=path.name)


class BearerAuthApp:
    def __init__(self, app, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in {"http", "websocket"} or scope.get("path", "").startswith(
            "/downloads/"
        ):
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        if headers.get(b"authorization") != f"Bearer {self.token}".encode():
            response = JSONResponse({"detail": "未授权"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_app():
    token = os.environ.get("DOUHOT_MCP_TOKEN", "").strip()
    if not token:
        raise RuntimeError("必须配置 DOUHOT_MCP_TOKEN")
    return BearerAuthApp(mcp.streamable_http_app(), token)


def main() -> None:
    host = os.environ.get("DOUHOT_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("DOUHOT_MCP_PORT", "8765"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
