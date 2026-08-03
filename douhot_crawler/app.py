"""爬虫运行编排。"""

import asyncio
import select
import signal
import sys
from collections.abc import Callable
from datetime import datetime

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from playwright.async_api import Page

from douhot_crawler.browser_patch import apply as _apply_browser_patch

_apply_browser_patch()

from .collector import collect_all_video_details
from .config import PROFILE_PATH, RESULT_EXCEL_PATH, TARGET_URL
from .models import RunOptions, VideoRecord
from .page_actions import (
    click_result_type,
    click_time_range,
    print_input_candidates,
    submit_search,
    wait_for_search_input,
)
from .storage import (
    excel_sheet_name,
    existing_video_identities,
    write_result_excel,
)


async def watch_stop_command(stop_event: asyncio.Event) -> None:
    """监听终端的 q 指令，在当前记录完成后安全停止。"""

    while not stop_event.is_set():
        try:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
        except (OSError, ValueError, TypeError):
            return

        if readable:
            command = sys.stdin.readline().strip().lower()
            if command in {"q", "quit", "exit"}:
                stop_event.set()
                print("已收到安全停止请求，将完成当前记录并写入已有数据后退出")
                return

        await asyncio.sleep(0.2)


async def run(
    options: RunOptions,
    *,
    stop_requested: Callable[[], bool] | None = None,
    profile_path=None,
    excel_path=None,
    max_results: int | None = None,
) -> dict:
    """执行一次完整的关键词搜索、采集和结果入库。"""

    if options.detail_delay < 0:
        raise ValueError("--detail-delay 不能小于 0")
    if max_results is not None and max_results < 1:
        raise ValueError("max_results 必须大于 0")

    profile_path = (profile_path or PROFILE_PATH).resolve()
    if not profile_path.exists():
        raise FileNotFoundError(
            f"没有找到 douhot Profile：{profile_path}\n"
            "请先运行 `uv run crwl profiles`，并确认已经按 q 保存。"
        )

    excel_path = (excel_path or RESULT_EXCEL_PATH).resolve()
    known_video_identities = existing_video_identities(excel_path, options.keyword)
    skipped_in_list = 0
    added_count = 0
    skipped_in_storage = 0
    stop_event = asyncio.Event()
    stop_task: asyncio.Task[None] | None = None
    signal_handler_installed = False

    def request_safe_stop() -> None:
        """请求在当前记录完成后落盘并退出，而不是中断写入。"""

        if not stop_event.is_set():
            stop_event.set()
            print("已收到停止请求，将完成当前记录并写入本页已有数据后退出")

    def should_stop() -> bool:
        """合并命令行、信号和桌面 GUI 的协作式停止请求。"""

        if stop_requested and stop_requested():
            request_safe_stop()
        return stop_event.is_set()

    # GUI 使用 SIGTERM 请求停止。将其转换为协作式停止事件，避免
    # process.terminate() 直接丢弃尚未写入的 page_records。
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, request_safe_stop)
        signal_handler_installed = True
    except (NotImplementedError, RuntimeError):
        # 非 POSIX 平台不支持 asyncio 信号处理时，仍可使用命令行 q。
        pass
    if known_video_identities:
        print(f"已加载 {len(known_video_identities)} 条已有视频，将跳过详情页")

    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=options.headless,
        use_managed_browser=True,
        use_persistent_context=True,
        user_data_dir=str(profile_path),
        viewport_width=1440,
        viewport_height=1000,
        verbose=True,
    )
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=120_000,
        delay_before_return_html=2.0,
    )
    crawler = AsyncWebCrawler(config=browser_config)

    if sys.stdin is not None and sys.stdin.isatty():
        print("输入 q 并按回车，可在当前记录完成后写入 Excel 并安全退出")
        stop_task = asyncio.create_task(watch_stop_command(stop_event))

    async def persist_page(records: list[VideoRecord], page_number: int) -> None:
        """将一页已采集记录增量写入 Excel 后释放内存。"""

        nonlocal added_count, skipped_in_storage
        crawled_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        page_added, page_skipped = await asyncio.to_thread(
            write_result_excel,
            records,
            excel_path,
            options.keyword,
            options.result_type,
            options.time_range,
            crawled_at,
        )
        added_count += page_added
        skipped_in_storage += page_skipped
        print(f"第 {page_number} 页已写入 Excel：新增 {page_added} 条")

    async def after_goto(
        page: Page,
        context,
        url: str,
        response,
        **kwargs,
    ) -> Page:
        nonlocal skipped_in_list
        print(f"\n页面已打开：{url}")
        await page.wait_for_load_state("domcontentloaded")
        await wait_for_search_input(page, options.input_timeout)
        await print_input_candidates(page)
        await submit_search(page, options.keyword, options.input_timeout)
        await click_result_type(page, options.result_type)
        await click_time_range(page, options.time_range)

        _, skipped_count, stopped = await collect_all_video_details(
            page,
            known_video_identities,
            options.detail_delay,
            persist_page,
            should_stop,
            max_results=max_results,
        )
        skipped_in_list += skipped_count
        if stopped:
            print("已安全停止采集")
        return page

    crawler.crawler_strategy.set_hook("after_goto", after_goto)

    try:
        await crawler.start()
        result = await crawler.arun(url=TARGET_URL, config=run_config)
        if not result.success:
            raise RuntimeError(result.error_message or "爬取失败")

        print(f"\n总结果 Excel：{excel_path}（Sheet：{excel_sheet_name(options.keyword)}）")
        print(
            f"本次新增 {added_count} 条，"
            f"跳过已有视频 {skipped_in_list + skipped_in_storage} 条"
        )
        return {
            "excel_path": str(excel_path),
            "added_count": added_count,
            "skipped_count": skipped_in_list + skipped_in_storage,
            "sheet": excel_sheet_name(options.keyword),
        }
    finally:
        if stop_task:
            stop_task.cancel()
            try:
                await stop_task
            except asyncio.CancelledError:
                pass
        if signal_handler_installed:
            asyncio.get_running_loop().remove_signal_handler(signal.SIGTERM)
        await crawler.close()
