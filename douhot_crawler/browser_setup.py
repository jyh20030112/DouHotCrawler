"""检查并安装供本地桌面版使用的 Chromium。"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path


def chromium_status() -> tuple[bool, str]:
    """返回 Playwright Chromium 是否已安装，以及可用于界面展示的说明。"""

    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        try:
            executable = Path(playwright.chromium.executable_path)
        finally:
            playwright.stop()
    except Exception as exc:
        return False, f"无法检查 Chromium：{exc}"

    if executable.is_file():
        return True, f"Chromium 已就绪：{executable}"
    return False, "尚未下载 Chromium；首次使用时下载一次即可。"


def install_chromium(report: Callable[[str], None]) -> None:
    """调用随应用分发的 Playwright 驱动下载 Chromium。"""

    from playwright._impl._driver import compute_driver_executable, get_driver_env

    node, cli = compute_driver_executable()
    report("开始下载 Chromium，下载时间取决于网络状况…")
    process = subprocess.Popen(
        [node, cli, "install", "chromium"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=get_driver_env(),
    )
    assert process.stdout is not None
    for line in process.stdout:
        if line.strip():
            report(line.rstrip())
    if process.wait() != 0:
        raise RuntimeError("Chromium 下载失败，请检查网络后重试。")

    available, detail = chromium_status()
    if not available:
        raise RuntimeError(detail)
    report("Chromium 下载完成。")
