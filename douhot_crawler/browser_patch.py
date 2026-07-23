"""将 _DOUHOT_CHANNEL 注入 Playwright 的 launch / launch_persistent_context。

crawl4ai 的 BrowserManager 在 use_persistent_context=True 时不传递 channel
参数，但 Playwright 底层（Node.js 驱动）在 _prepareToLaunch 中完全支持。
本模块通过 monkey-patch browser_type 的两个入口方法，让系统 Chrome/Edge
可以在不修改 crawl4ai 源码的情况下被使用。
"""

from __future__ import annotations

import os

from playwright.async_api import BrowserType

_patched = False


def apply() -> None:
    """注入 channel 到 Playwright 启动方法中（幂等）。"""
    global _patched
    if _patched:
        return

    channel = os.environ.get("_DOUHOT_CHANNEL")
    if not channel:
        return

    _original_lpc = BrowserType.launch_persistent_context

    async def _patched_lpc(self: BrowserType, user_data_dir, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("channel", channel)
        return await _original_lpc(self, user_data_dir, **kwargs)

    BrowserType.launch_persistent_context = _patched_lpc  # type: ignore[method-assign]

    _original_launch = BrowserType.launch

    async def _patched_launch(self: BrowserType, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("channel", channel)
        return await _original_launch(self, **kwargs)

    BrowserType.launch = _patched_launch  # type: ignore[method-assign]

    _patched = True
