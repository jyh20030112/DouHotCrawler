"""爬虫运行编排。"""

import asyncio
from datetime import datetime

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from playwright.async_api import Page

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


async def run(options: RunOptions) -> None:
    """执行一次完整的关键词搜索、采集和结果入库。"""

    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"没有找到 douhot Profile：{PROFILE_PATH}\n"
            "请先运行 `uv run crwl profiles`，并确认已经按 q 保存。"
        )

    excel_path = RESULT_EXCEL_PATH.resolve()
    captured_videos: list[VideoRecord] = []
    known_video_identities = existing_video_identities(excel_path, options.keyword)
    skipped_in_list = 0
    if known_video_identities:
        print(f"已加载 {len(known_video_identities)} 条已有视频，将跳过详情页")

    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=options.headless,
        use_managed_browser=True,
        use_persistent_context=True,
        user_data_dir=str(PROFILE_PATH),
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

        new_records, skipped_count = await collect_all_video_details(
            page,
            known_video_identities,
        )
        captured_videos.extend(new_records)
        skipped_in_list += skipped_count
        return page

    crawler.crawler_strategy.set_hook("after_goto", after_goto)

    try:
        await crawler.start()
        result = await crawler.arun(url=TARGET_URL, config=run_config)
        if not result.success:
            raise RuntimeError(result.error_message or "爬取失败")

        crawled_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        added_count, skipped_count = write_result_excel(
            records=captured_videos,
            excel_path=excel_path,
            keyword=options.keyword,
            result_type=options.result_type,
            time_range=options.time_range,
            crawled_at=crawled_at,
        )
        print(f"\n总结果 Excel：{excel_path}（Sheet：{excel_sheet_name(options.keyword)}）")
        print(
            f"本次新增 {added_count} 条，"
            f"跳过已有视频 {skipped_in_list + skipped_count} 条"
        )
    finally:
        await crawler.close()
