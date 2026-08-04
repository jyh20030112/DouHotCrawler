from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from douhot_crawler.api.app import create_app
from douhot_crawler.api.clients import ExternalApiClient
from douhot_crawler.api.config import ApiSettings
from douhot_crawler.api import daily
from douhot_crawler.api.models import (
    PipelineTaskRequest,
    TaskKind,
    TaskStatus,
    UploadTaskRequest,
)
from douhot_crawler.api.service import ApiTaskService, parse_follower_count
from douhot_crawler.api.store import ApiTaskStore
from douhot_crawler.api.errors import ExternalServiceError, TaskPaused
from douhot_crawler.core.config import RESULT_HEADERS
from douhot_crawler.core.storage import atomic_workbook_save


def settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        hotspot_api_url="https://example.test/hotspots",
        cookie_api_url="https://example.test/cookies",
        ranking_api_url="https://example.test/rankings",
        extract_api_url="https://example.test/extract",
        hotspot_open_id="test-open-id",
        data_root=tmp_path,
    )


def test_settings_accepts_single_worker_from_environment(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DOUHOT_HOTSPOT_API_URL", "https://example.test/hotspots")
    monkeypatch.setenv("DOUHOT_COOKIE_API_URL", "https://example.test/cookies")
    monkeypatch.setenv("DOUHOT_RANKING_API_URL", "https://example.test/rankings")
    monkeypatch.setenv("EXTRACT_API_URL", "https://example.test/extract")
    monkeypatch.setenv("DOUHOT_HOTSPOT_OPEN_ID", "test-open-id")
    monkeypatch.setenv("DOUHOT_API_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("DOUHOT_API_WORKERS", "1")
    monkeypatch.setenv("DOUHOT_MAX_VIDEOS_PER_KEYWORD", "17")

    configured = ApiSettings()
    assert configured.workers == 1
    assert configured.max_videos_per_keyword == 17


def test_task_store_fifo_pause_resume_and_restart_recovery(tmp_path: Path) -> None:
    path = tmp_path / "tasks.sqlite3"
    store = ApiTaskStore(path)
    first = store.create(TaskKind.CRAWL, {"keyword": "甲"})
    second = store.create(TaskKind.PIPELINE, {})

    assert store.claim_next()["task_id"] == first["task_id"]
    store.request_pause(first["task_id"])
    assert store.get(first["task_id"])["status"] == TaskStatus.PAUSING
    store.mark_paused(first["task_id"], "user")
    store.resume(first["task_id"])
    assert store.get(first["task_id"])["status"] == TaskStatus.QUEUED

    # FIFO preserves the older resumed task ahead of the later pipeline.
    assert store.claim_next()["task_id"] == first["task_id"]
    restarted = ApiTaskStore(path)
    assert restarted.get(first["task_id"])["status"] == TaskStatus.FAILED
    assert restarted.claim_next()["task_id"] == second["task_id"]
    restarted_again = ApiTaskStore(path)
    assert restarted_again.get(second["task_id"])["status"] == TaskStatus.QUEUED
    assert restarted_again.get(second["task_id"])["pause_reason"] == "shutdown"


@pytest.mark.asyncio
async def test_external_client_extracts_unique_keywords_and_cookie(tmp_path: Path) -> None:
    calls: list[tuple[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        calls.append((request.url.path, payload))
        if request.url.path == "/hotspots":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "message": "操作成功",
                    "data": {
                        "records": [
                            {"title": " 甲 "},
                            {"title": "甲"},
                            {"title": None},
                            {"title": "乙"},
                        ]
                    },
                },
            )
        return httpx.Response(
            200, json={"code": 200, "message": "操作成功", "cookie": "sid=secret"}
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ExternalApiClient(settings(tmp_path), client=http_client)
    assert await client.fetch_keywords() == ["甲", "乙"]
    assert await client.fetch_cookie(0) == "sid=secret"
    assert calls == [
        ("/hotspots", {"openId": "test-open-id", "size": 30}),
        ("/cookies", {"type": 0}),
    ]
    await http_client.aclose()


@pytest.mark.asyncio
async def test_external_client_accepts_cookie_in_data_field(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 200, "message": "操作成功", "data": "sid=from-data"},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ExternalApiClient(settings(tmp_path), client=http_client)
    assert await client.fetch_cookie(0) == "sid=from-data"
    await http_client.aclose()


@pytest.mark.asyncio
async def test_external_client_preserves_hotspot_business_error(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 400, "message": "openId无效"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ExternalApiClient(settings(tmp_path), client=http_client)
    with pytest.raises(ExternalServiceError, match="openId无效"):
        await client.fetch_keywords()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_external_client_retries_5xx_three_times(tmp_path: Path, monkeypatch) -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            return httpx.Response(503)
        return httpx.Response(200, json={"code": 200, "message": "ok"})

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("douhot_crawler.api.clients.asyncio.sleep", no_sleep)
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ExternalApiClient(settings(tmp_path), client=http_client)
    await client.upload_rankings([{"videoUrl": "https://example.test/video/1"}])
    assert attempts == 4
    await http_client.aclose()


@pytest.mark.asyncio
async def test_external_client_retries_business_5xx_three_times(
    tmp_path: Path, monkeypatch
) -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            return httpx.Response(
                200, json={"code": 500, "message": "请求处理异常，请稍后再试"}
            )
        return httpx.Response(
            200, json={"code": 200, "message": "操作成功", "data": "sid=ok"}
        )

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("douhot_crawler.api.clients.asyncio.sleep", no_sleep)
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ExternalApiClient(settings(tmp_path), client=http_client)
    assert await client.fetch_cookie(0) == "sid=ok"
    assert attempts == 4
    await http_client.aclose()


def test_follower_count_parser() -> None:
    assert parse_follower_count("1.2万") == (12_000, False)
    assert parse_follower_count("3.45亿") == (345_000_000, False)
    assert parse_follower_count("12,345") == (12_345, False)
    assert parse_follower_count(12.6) == (13, False)
    assert parse_follower_count("") == (0, True)
    assert parse_follower_count("未知") == (0, True)


class FakeExternalClient:
    def __init__(self) -> None:
        self.uploads: list[list[dict[str, Any]]] = []

    async def fetch_keywords(self) -> list[str]:
        return ["甲", "乙"]

    async def fetch_cookie(self, cookie_type: int) -> str:
        return f"type={cookie_type}"

    async def upload_rankings(self, records: list[dict[str, Any]]) -> None:
        self.uploads.append(records)

    async def close(self) -> None:
        return None


def create_upload_workbook(path: Path, *, rows: int) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "关键词"
    sheet.append([*RESULT_HEADERS, "视频口播"])
    for index in range(rows):
        sheet.append(
            [
                index + 1,
                "低粉爆款",
                "2026-08-04 03:00:00",
                "近7天",
                f"视频{index}",
                f"https://www.douyin.com/video/{index}",
                f"作者{index}",
                "1万",
                "50万",
                "20万",
                "1万",
                "5%",
                "好评",
                "口播",
            ]
        )
    atomic_workbook_save(workbook, path)
    workbook.close()


@pytest.mark.asyncio
async def test_failed_upload_batch_is_resumable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "douhot_crawler.api.service.chromium_status", lambda: (True, "test browser")
    )

    class FailOnceClient(FakeExternalClient):
        def __init__(self) -> None:
            super().__init__()
            self.fail = True

        async def upload_rankings(self, records: list[dict[str, Any]]) -> None:
            self.uploads.append(records)
            if self.fail:
                self.fail = False
                raise RuntimeError("temporary upload failure")

    fake_client = FailOnceClient()
    service = ApiTaskService(settings(tmp_path), client=fake_client)
    task, _ = service.create_pipeline(PipelineTaskRequest(keywords=["关键词"]))
    workbook = service._workbook(task["task_id"])
    workbook.parent.mkdir(parents=True, exist_ok=True)
    create_upload_workbook(workbook, rows=2)

    with pytest.raises(TaskPaused, match="upload_failure"):
        await service._upload_sheet(task["task_id"], workbook, "关键词")
    await service._upload_sheet(task["task_id"], workbook, "关键词")
    assert [len(batch) for batch in fake_client.uploads] == [2, 2]


@pytest.mark.asyncio
async def test_standalone_upload_task_sends_existing_workbook(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "douhot_crawler.api.service.chromium_status", lambda: (True, "test browser")
    )
    fake_client = FakeExternalClient()
    service = ApiTaskService(settings(tmp_path), client=fake_client)
    source = service.store.create(TaskKind.CRAWL, {"keyword": "关键词"})
    workbook = service._workbook(source["task_id"])
    workbook.parent.mkdir(parents=True, exist_ok=True)
    create_upload_workbook(workbook, rows=21)
    service.store.finish(
        source["task_id"],
        result={"artifact": service._artifact(workbook)},
        artifact_path=workbook,
    )

    upload = service.create_upload(
        UploadTaskRequest(source_task_id=source["task_id"], sheets=None)
    )
    await service._execute(service.store.claim_next())

    completed = service.status(upload["task_id"])
    assert completed["status"] == TaskStatus.SUCCEEDED
    assert completed["result"]["sheets"] == ["关键词"]
    assert completed["result"]["eligible_rows"] == 21
    assert completed["result"]["sent_rows"] == 21
    assert [len(batch) for batch in fake_client.uploads] == [20, 1]


@pytest.mark.asyncio
async def test_pipeline_runs_keywords_sequentially_and_uploads_batches(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "douhot_crawler.api.service.chromium_status", lambda: (True, "test browser")
    )
    fake_client = FakeExternalClient()
    service = ApiTaskService(settings(tmp_path), client=fake_client)
    execution_order: list[str] = []
    crawl_limits: list[int] = []

    async def fake_crawler(options, **kwargs):
        execution_order.append(f"crawl:{options.keyword}")
        crawl_limits.append(kwargs["max_results"])
        path = Path(kwargs["excel_path"])
        if path.exists():
            workbook = load_workbook(path)
            sheet = workbook.create_sheet(options.keyword)
        else:
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = options.keyword
        sheet.append(RESULT_HEADERS)
        for index in range(21):
            sheet.append(
                [
                    index + 1,
                    options.result_type,
                    "2026-08-04 03:00:00",
                    options.time_range,
                    f"视频{index}",
                    f"https://www.douyin.com/video/{options.keyword}{index}",
                    f"作者{index}",
                    "1.2万" if index else "未知",
                    "50万",
                    "20万",
                    "1万",
                    "5%",
                    "好评",
                ]
            )
        atomic_workbook_save(workbook, path)
        workbook.close()
        return {
            "excel_path": str(path),
            "added_count": 21,
            "skipped_count": 0,
            "sheet": options.keyword,
            "stopped": False,
        }

    def fake_analyze(args, *, stop_requested):
        execution_order.append(f"analyze:{args.sheet[0]}")
        workbook = load_workbook(args.excel)
        sheet = workbook[args.sheet[0]]
        sheet.cell(row=1, column=14, value="视频口播")
        for row in range(2, sheet.max_row + 1):
            sheet.cell(row=row, column=14, value="测试口播")
        atomic_workbook_save(workbook, args.excel)
        workbook.close()
        return 21, 0, 0

    monkeypatch.setattr("douhot_crawler.api.service.run_crawler", fake_crawler)
    monkeypatch.setattr("douhot_crawler.api.service.analyze_excel", fake_analyze)

    task, created = service.create_pipeline(PipelineTaskRequest())
    assert created is True
    claimed = service.store.claim_next()
    await service._execute(claimed)

    completed = service.status(task["task_id"])
    assert completed["status"] == TaskStatus.SUCCEEDED_WITH_WARNINGS
    assert completed["result"]["keywords_succeeded"] == 2
    assert execution_order == ["crawl:甲", "analyze:甲", "crawl:乙", "analyze:乙"]
    assert crawl_limits == [3, 3]
    assert [len(batch) for batch in fake_client.uploads] == [20, 1, 20, 1]
    assert all(
        isinstance(row["followerCount"], int)
        for batch in fake_client.uploads
        for row in batch
    )


class FakeRouteService:
    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "worker_running": True,
            "database_ok": True,
            "browser_ok": True,
            "external_urls_configured": True,
            "scheduler_overlap": False,
        }

    async def keywords(self) -> list[str]:
        return ["关键词"]

    def create_pipeline(self, request):
        return {"task_id": "id", "status": "queued"}, True

    def create_upload(self, request):
        return {"task_id": "upload-id", "status": "queued"}


def test_api_routes_and_validation_envelope(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path), service=FakeRouteService())
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"
        assert client.get("/api/v1/keywords").json() == {"key_word": ["关键词"]}
        accepted = client.post("/api/v1/tasks/pipeline", json={})
        assert accepted.status_code == 202
        assert accepted.json() == {"task_id": "id", "status": "queued", "created": True}
        invalid = client.post(
            "/api/v1/tasks/pipeline",
            json={"keywords": [f"词{index}" for index in range(31)]},
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
        uploaded = client.post(
            "/api/v1/tasks/upload",
            json={
                "source_task_id": "42118d44-6334-4a0c-a9a5-9a5096ab2962",
                "sheets": None,
            },
        )
        assert uploaded.status_code == 202
        assert uploaded.json()["task_id"] == "upload-id"


def test_openapi_documents_workflow_examples_and_errors(tmp_path: Path) -> None:
    schema = create_app(settings(tmp_path), service=FakeRouteService()).openapi()

    assert "FIFO" in schema["info"]["description"]
    assert [item["name"] for item in schema["tags"]] == [
        "系统",
        "关键词",
        "任务创建",
        "任务控制",
    ]
    crawl = schema["paths"]["/api/v1/tasks/crawl"]["post"]
    assert crawl["summary"] == "创建单关键词爬取任务"
    assert crawl["tags"] == ["任务创建"]
    assert crawl["responses"]["202"]["description"] == "Successful Response"
    assert "ErrorResponse" in str(crawl["responses"]["502"])
    request_schema = schema["components"]["schemas"]["CrawlTaskRequest"]
    assert request_schema["examples"][0]["keyword"] == "大健康"
    assert "最多采集条数" in request_schema["properties"]["limit"]["description"]
    task_schema = schema["components"]["schemas"]["TaskResponse"]
    assert task_schema["examples"][0]["progress"]["current"] == 3
    upload = schema["paths"]["/api/v1/tasks/upload"]["post"]
    assert upload["summary"] == "上传现有 Excel 的全部合格数据"


def test_daily_launcher_submits_once_and_prints_task_id(monkeypatch, capsys) -> None:
    request: dict[str, Any] = {}

    def fake_post(url: str, *, json: dict[str, Any], timeout: float):
        request.update(url=url, json=json, timeout=timeout)
        return httpx.Response(
            202,
            json={"task_id": "pipeline-id", "status": "queued", "created": True},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setenv("DOUHOT_DAILY_API_URL", "http://127.0.0.1:9999/")
    monkeypatch.setattr(daily.httpx, "post", fake_post)
    daily.main()

    assert request == {
        "url": "http://127.0.0.1:9999/api/v1/tasks/pipeline",
        "json": {},
        "timeout": 30.0,
    }
    assert "task_id=pipeline-id status=queued created=true" in capsys.readouterr().out
