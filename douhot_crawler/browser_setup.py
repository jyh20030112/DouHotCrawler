"""检查并安装供本地桌面版使用的 Chromium 浏览器。

优先使用系统已安装的 Chrome / Edge；如未找到则下载 Playwright 自带的
Chromium。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

# Playwright 驱动的 PyInstaller hook 会将 PLAYWRIGHT_BROWSERS_PATH 设为 "0"，
# 使浏览器缓存落入 PyInstaller 临时目录，重启后丢失。我们必须在任何 Playwright
# API 调用之前将其固定到系统默认缓存目录，这样已下载的 Chromium 才能持久化。
_DOUHOT_CHANNEL_ENV = "_DOUHOT_CHANNEL"

_CHROMIUM_INSTALL_TIMEOUT = 600  # 下载 + 解压最长等待时间（秒）


# ── 默认缓存路径 ──────────────────────────────────────────────────────


def _default_browsers_cache() -> Path:
    """返回当前平台的 Playwright 默认浏览器缓存目录。"""
    if sys.platform == "win32":
        base = os.environ.get(
            "LOCALAPPDATA", str(Path.home() / "AppData" / "Local")
        )
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Caches")
    else:
        base = os.environ.get(
            "XDG_CACHE_HOME", str(Path.home() / ".cache")
        )
    return Path(base) / "ms-playwright"


def _ensure_persistent_cache() -> None:
    """将 PLAYWRIGHT_BROWSERS_PATH 固定到持久目录。

    必须在任何 Playwright API 调用之前执行。因为 get_driver_env() 会
    copy os.environ，而 _transport.py 随后对这份拷贝做 setdefault("0")；
    这里的 setdefault 会抢先一步，让后续的 "0" 覆盖变成 no-op。
    """
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH", str(_default_browsers_cache())
    )


# ── 系统浏览器检测 ────────────────────────────────────────────────────


def detect_system_browser() -> tuple[str | None, str | None]:
    """检测系统已安装的 Chromium 内核浏览器。

    Returns:
        (channel, executable_path)。channel 为 Playwright 识别的渠道名
        （\"chrome\"、\"msedge\"、\"chromium\"），未找到时返回 (None, None)。
    """
    if sys.platform == "win32":
        candidates: list[tuple[str, str]] = [
            (
                "chrome",
                os.path.expandvars(
                    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"
                ),
            ),
            (
                "chrome",
                os.path.expandvars(
                    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
                ),
            ),
            (
                "chrome",
                os.path.expandvars(
                    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
                ),
            ),
            (
                "msedge",
                os.path.expandvars(
                    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
                ),
            ),
            (
                "msedge",
                os.path.expandvars(
                    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
                ),
            ),
        ]
    elif sys.platform == "darwin":
        candidates = [
            (
                "chrome",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ),
            (
                "msedge",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ),
        ]
    else:
        candidates = [
            ("chrome", "/usr/bin/google-chrome-stable"),
            ("chrome", "/usr/bin/google-chrome"),
            ("chromium", "/usr/bin/chromium-browser"),
            ("chromium", "/usr/bin/chromium"),
            ("msedge", "/usr/bin/microsoft-edge-stable"),
            ("msedge", "/usr/bin/microsoft-edge"),
        ]

    for channel, path in candidates:
        if Path(path).is_file():
            return channel, path
    return None, None


def _browser_label(executable_path: str) -> str:
    """根据路径返回友好的浏览器名称。"""
    lower = executable_path.lower()
    if "edge" in lower:
        return "Edge "
    if "chromium" in lower and "chrome" not in lower:
        return "Chromium "
    return "Chrome "


# ── 公开 API ──────────────────────────────────────────────────────────


def chromium_status() -> tuple[bool, str]:
    """返回浏览器是否可用及说明。

    优先检测系统 Chrome / Edge；未找到时回退到 Playwright 自带的 Chromium。
    调用方不需要关心具体用了哪种浏览器。
    """

    # 在触碰 Playwright 之前固定缓存路径，防止 PyInstaller 的 "0" 覆盖。
    _ensure_persistent_cache()

    channel, path = detect_system_browser()
    if channel:
        # 将 channel 存入环境变量，供 browser_patch.py 读取并注入到
        # Playwright 的 launch / launch_persistent_context 调用中。
        os.environ[_DOUHOT_CHANNEL_ENV] = channel
        return True, f"{_browser_label(path)}已就绪：{path}"

    # 没有系统浏览器 → 检查 Playwright 自带的 Chromium
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

    detail = f"尚未下载 Chromium（期望位置：{executable}）"
    if cache_dir.is_dir():
        try:
            entries = sorted(
                p.name for p in cache_dir.iterdir()  # type: ignore[union-attr]
            )
        except OSError:
            entries = []
        if entries:
            detail += f"；缓存目录已有：{', '.join(entries[:8])}"
    return False, detail


def install_chromium(report: Callable[[str], None]) -> None:
    """调用随应用分发的 Playwright 驱动下载 Chromium。

    在单独的线程中实时读取 stdout 以保证流式输出；
    stdin=DEVNULL 避免 Windows GUI 进程的 stdin 句柄导致子进程阻塞。
    """

    from playwright._impl._driver import compute_driver_executable, get_driver_env

    _ensure_persistent_cache()

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
