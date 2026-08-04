from __future__ import annotations

import inspect

from douhot_crawler.interfaces import mcp as mcp_server


def test_crawl_tool_defaults_to_ten_results():
    parameter = inspect.signature(mcp_server.douhot_crawl_start).parameters["limit"]
    assert parameter.default == 10


def test_streamable_http_uses_sse_responses_for_progress_notifications():
    assert mcp_server.mcp.settings.json_response is False


async def test_lifespan_waits_for_job_shutdown_before_completing():
    events = []
    messages = iter(
        [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
    )

    class Manager:
        def request_shutdown(self):
            events.append("requested")

        async def shutdown(self):
            events.append("jobs-stopped")

    async def app(_scope, receive, send):
        assert await receive() == {"type": "lifespan.startup"}
        await send({"type": "lifespan.startup.complete"})
        assert await receive() == {"type": "lifespan.shutdown"}
        await send({"type": "lifespan.shutdown.complete"})

    async def receive():
        return next(messages)

    async def send(message):
        events.append(message["type"])

    managed_app = mcp_server.ManagedLifespanApp(app, Manager())
    await managed_app({"type": "lifespan"}, receive, send)

    assert events == [
        "lifespan.startup.complete",
        "requested",
        "jobs-stopped",
        "lifespan.shutdown.complete",
    ]


async def test_job_wait_reports_progress_and_returns_terminal_result(monkeypatch):
    progress = []

    class Context:
        async def report_progress(self, current, total=None, message=None):
            progress.append((current, total, message))

    async def wait_for_terminal(
        user_id, job_id, *, kinds, timeout, poll_interval, on_status
    ):
        assert (user_id, job_id) == ("alice", "job-1")
        assert kinds == ("crawl", "analyze")
        assert timeout == 12
        await on_status({"status": "running"})
        await on_status({"status": "succeeded"})
        return {"id": job_id, "status": "succeeded"}

    monkeypatch.setattr(mcp_server.manager, "wait_for_terminal", wait_for_terminal)

    result = await mcp_server.douhot_job_wait(
        "alice", Context(), "job-1", timeout_seconds=12
    )

    assert result == {"id": "job-1", "status": "succeeded"}
    assert progress == [
        (0.0, 12, "DouHot 任务状态：running"),
        (1.0, 12, "DouHot 任务状态：succeeded"),
    ]
