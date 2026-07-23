"""打开 Douhot 登录页，供用户扫码更新爬虫 Profile。"""

from __future__ import annotations

import asyncio
import select
import signal
import sys
from collections.abc import Callable

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

from douhot_crawler.browser_patch import apply as _apply_browser_patch

_apply_browser_patch()

from .config import LOGIN_URL, PROFILE_PATH


async def _wait_for_completion(
    stop_event: asyncio.Event,
    stop_requested: Callable[[], bool] | None = None,
) -> None:
    """等待终端或 GUI 写入 q；不读取或打印任何登录凭据。"""

    print("请在浏览器中扫码登录。完成后输入 q 并回车，或点击“已完成扫码，保存登录”。")
    while not stop_event.is_set():
        if stop_requested and stop_requested():
            print("已收到停止请求，正在保存登录状态…")
            stop_event.set()
            continue
        try:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
        except (OSError, ValueError):
            readable = []
        if readable:
            command = sys.stdin.readline()
            if command.strip().lower() in {"q", "quit", "exit"}:
                stop_event.set()
        await asyncio.sleep(0.2)


def _login_run_config() -> CrawlerRunConfig:
    """返回不会被单页爬取收回的登录页配置。"""

    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=120_000,
        delay_before_return_html=1.0,
        # 未设置 session_id 时，Crawl4AI 会在 arun() 完成后回收该页面。
        # 登录页必须保持到用户扫码并明确确认保存为止。
        session_id="douhot-login",
    )


async def run_login(*, stop_requested: Callable[[], bool] | None = None) -> None:
    """使用爬虫同一持久化 Profile 打开 Douhot 首页并等待扫码。"""

    stop_event = asyncio.Event()
    signal_handler_installed = False

    def request_stop() -> None:
        if not stop_event.is_set():
            print("正在保存登录状态并关闭浏览器…")
            stop_event.set()

    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, request_stop)
        signal_handler_installed = True
    except (NotImplementedError, RuntimeError):
        pass

    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=False,
        use_managed_browser=True,
        use_persistent_context=True,
        user_data_dir=str(PROFILE_PATH),
        viewport_width=1440,
        viewport_height=1000,
        verbose=True,
    )
    run_config = _login_run_config()
    crawler = AsyncWebCrawler(config=browser_config)

    try:
        await crawler.start()
        result = await crawler.arun(url=LOGIN_URL, config=run_config)
        if not result.success:
            # 登录页是高度动态的应用页面。Crawl4AI 的内容提取可能把它误判为
            # 反爬（例如尚未生成 body），但浏览器中的页面已经成功打开；扫码
            # 不依赖提取结果，因此不能在这里提前关闭浏览器。
            print(
                "登录页已打开；页面内容解析未通过，可忽略并继续扫码："
                f"{result.error_message or '未知解析错误'}"
            )
        print(f"登录页面已打开：{LOGIN_URL}")
        await _wait_for_completion(stop_event, stop_requested)
        print("正在保存登录状态…")
    finally:
        if signal_handler_installed:
            asyncio.get_running_loop().remove_signal_handler(signal.SIGTERM)
        await crawler.close()
        print("浏览器已关闭，登录状态已保存。")
