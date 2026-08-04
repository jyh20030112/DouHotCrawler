from __future__ import annotations

import argparse
from io import BytesIO
from urllib.error import HTTPError

import pytest
from openpyxl import Workbook

from douhot_crawler.transcript import analyzer


def test_extract_transcript_includes_safe_http_error_detail(monkeypatch) -> None:
    error = HTTPError(
        "https://example.test/extract",
        400,
        "bad request",
        {},
        BytesIO(b'{"detail":"cookie sessionid=secret is invalid"}'),
    )
    def raise_error(*args, **kwargs):
        raise error

    monkeypatch.setattr(analyzer, "urlopen", raise_error)

    with pytest.raises(RuntimeError) as caught:
        analyzer.extract_transcript(
            "https://www.douyin.com/video/1",
            "sessionid=secret",
            "",
            1.0,
            api_url="https://example.test/extract",
        )

    assert "HTTP 400" in str(caught.value)
    assert "[REDACTED]" in str(caught.value)
    assert "sessionid=secret" not in str(caught.value)


def test_analyze_logs_running_and_final_success_counts(
    tmp_path, monkeypatch, capsys
) -> None:
    excel_path = tmp_path / "result.xlsx"
    cookie_path = tmp_path / "cookie.config"
    cookie_path.write_text("sessionid=test-only", encoding="utf-8")

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "老板创业"
    worksheet.append(["视频的url"])
    worksheet.append(["https://www.douyin.com/video/1"])
    worksheet.append(["https://www.douyin.com/video/2"])
    workbook.save(excel_path)
    workbook.close()

    monkeypatch.setattr(analyzer, "extract_transcript", lambda **_: "测试口播")
    result = analyzer.analyze_excel(
        argparse.Namespace(
            excel=excel_path,
            cookie_file=cookie_path,
            sheet=None,
            callback_url="",
            timeout=1.0,
            delay=0.0,
            limit=None,
            overwrite=False,
        )
    )

    assert result == (2, 0, 0)
    output = capsys.readouterr().out
    assert "第 2 行口播已写入（本次已完成 1 个）" in output
    assert "第 3 行口播已写入（本次已完成 2 个）" in output
    assert "口播提取完成：成功 2 个，跳过 0 个，失败 0 个" in output
