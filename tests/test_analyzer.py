from __future__ import annotations

import argparse

from openpyxl import Workbook

from douhot_crawler.transcript import analyzer


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
