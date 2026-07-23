"""检查并安装供本地桌面版使用的 Chromium。"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

# Playwright 在所有启动路径中都会读取该环境变量，用于指定 Chromium 可执行文件。
_ENV_EXECUTABLE_PATH = "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"


def detect_system_browser() -> str | None:
    """检测系统已安装的 Chrome / Edge / Chromium，返回可执行文件路径。"""

    if sys.platform == "win32":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
            ),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/microsoft-edge",
            "/usr/bin/microsoft-edge-stable",
        ]

    for path in candidates:
        if Path(path).is_file():
            return path
    return None


def chromium_status() -> tuple[bool, str]:
    """返回浏览器是否可用，以及可用于界面展示的说明。

    优先检测系统安装的 Chrome / Edge；如未找到则回退到 Playwright
    自带的 Chromium。
    """

    system = detect_system_browser()
    if system:
        os.environ.setdefault(_ENV_EXECUTABLE_PATH, system)
        browser_name = _browser_label(system)
        return True, f"{browser_name}已就绪：{system}"

    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        try:
            executable = Path(playwright.chromium.executable_path)
            cache_dir = Path(playwright.chromium.executable_path).parent.parent
        finally:
            playwright.stop()
    except Exception as exc:
        return False, f"无法检查 Chromium：{exc}"

    if executable.is_file():
        return True, f"Chromium 已就绪：{executable}"

    # 列出缓存目录内容帮助诊断
    detail = f"尚未下载 Chromium（期望位置：{executable}）"
    if cache_dir.is_dir():
        try:
            entries = sorted(p.name for p in cache_dir.iterdir())  # type: ignore[union-attr]
        except OSError:
            entries = []
        if entries:
            detail += f"；缓存目录已有：{', '.join(entries[:8])}"
    return False, detail


def _browser_label(executable_path: str) -> str:
    """根据路径返回友好的浏览器名称。"""

    lower = executable_path.lower()
    if "edge" in lower:
        return "Edge "
    if "chromium" in lower and "chrome" not in lower:
        return "Chromium "
    return "Chrome "


_CHROMIUM_INSTALL_TIMEOUT = 600  # 下载 + 解压最长等待时间（秒）


def install_chromium(report: Callable[[str], None]) -> None:
    """调用随应用分发的 Playwright 驱动下载 Chromium。

    在单独的线程中实时读取 stdout 以保证流式输出；
    stdin=DEVNULL 避免 Windows GUI 进程的 stdin 句柄导致子进程阻塞。
    """

    from playwright._impl._driver import compute_driver_executable, get_driver_env

    node, cli = compute_driver_executable()
    report("开始下载 Chromium，下载时间取决于网络状况…")

    # Windows：隐藏 Node 控制台窗口，并用 start_new_session 切断句柄继承
    popen_kwargs: dict = {}
    if sys.platform == "win32":
        popen_kwargs.update(
            creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
            start_new_session=True,
        )

    process = subprocess.Popen(
        [node, cli, "install", "chromium"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=get_driver_env(),
        **popen_kwargs,
    )
    assert process.stdout is not None

    # 在后台线程中读取 stdout，实现流式实时输出
    def _read_output() -> None:
        for line in process.stdout:  # type: ignore[union-attr]
            stripped = line.strip()
            if stripped:
                report(stripped)

    reader = threading.Thread(target=_read_output, daemon=True)
    reader.start()

    try:
        returncode = process.wait(timeout=_CHROMIUM_INSTALL_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        reader.join(timeout=5)
        # Playwright CLI 在 Windows 上可能在解压后挂起，但文件实际已就绪
        available, detail = chromium_status()
        if available:
            report("Chromium 下载完成。")
            return
        raise RuntimeError(
            f"Chromium 下载超时（{_CHROMIUM_INSTALL_TIMEOUT} 秒），请检查网络后重试。"
        )

    reader.join(timeout=5)

    if returncode != 0:
        raise RuntimeError("Chromium 下载失败，请检查网络后重试。")

    available, detail = chromium_status()
    if not available:
        raise RuntimeError(detail)
    report("Chromium 下载完成。")
