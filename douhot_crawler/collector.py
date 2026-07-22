"""榜单行解析、详情页采集与分页控制。"""

import gc
import re
import sys
from random import uniform
from collections.abc import Awaitable, Callable

from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .comments import fetch_top_comments
from .config import DETAIL_DELAY_JITTER
from .models import VideoIdentity, VideoRecord, video_identity


PagePersistor = Callable[[list[VideoRecord], int], Awaitable[None]]
StopRequested = Callable[[], bool]


async def extract_video_list_fields(row: Locator, title: str) -> dict[str, str]:
    """从榜单列表行提取博主与指标字段。"""

    cells = row.locator("td")
    if await cells.count() < 7:
        raise RuntimeError("榜单列表列数不足，无法提取视频指标")

    video_info_lines = [
        line.strip()
        for line in (await cells.nth(1).inner_text()).splitlines()
        if line.strip()
    ]
    fan_line_index = next(
        (
            index
            for index, line in enumerate(video_info_lines)
            if line.startswith("总粉丝数：")
        ),
        None,
    )
    if fan_line_index is None or fan_line_index == 0:
        raise RuntimeError(f"未能从视频信息中提取博主粉丝数：{title}")

    metrics = [
        (await cells.nth(index).inner_text()).strip()
        for index in range(2, 6)
    ]
    return {
        "author_name": video_info_lines[fan_line_index - 1],
        "total_followers": video_info_lines[fan_line_index]
        .removeprefix("总粉丝数：")
        .strip(),
        "hotness": metrics[0],
        "new_views": metrics[1],
        "new_likes": metrics[2],
        "like_rate": metrics[3],
    }


async def extract_video_list_record(
    row: Locator,
    page_number: int,
    row_number: int,
) -> VideoRecord:
    """提取列表页中可用于去重和写入 Excel 的字段。"""

    title_locator = row.locator('[class*="video-title"]').first
    if not await title_locator.is_visible():
        raise RuntimeError(f"第 {page_number} 页第 {row_number} 行没有发现视频名称")

    title = (await title_locator.inner_text()).strip()
    return {"title": title, **await extract_video_list_fields(row, title)}


async def capture_video_detail(
    page: Page,
    row: Locator,
    row_number: int,
    record: VideoRecord,
) -> VideoRecord:
    """打开一条视频详情页，提取 video_id 与高赞评论。"""

    title = record["title"]
    view_button = row.get_by_role("button", name="查看", exact=True)
    last_error: Exception | None = None

    for attempt in range(1, 4):
        popup: Page | None = None
        pages_before = set(page.context.pages)

        try:
            async with page.expect_popup(timeout=8_000) as popup_info:
                await view_button.click(timeout=5_000, force=attempt == 3)

            popup = await popup_info.value
            await popup.wait_for_url(
                re.compile(r"/video/detail\?video_id=\d+"),
                timeout=10_000,
            )
            match = re.search(r"[?&]video_id=(\d+)", popup.url)
            if not match:
                raise RuntimeError(f"详情 URL 中没有 video_id：{popup.url}")

            video_id = match.group(1)
            top_comments = ""
            try:
                top_comments = await fetch_top_comments(popup)
            except Exception as exc:
                print(f"  [{row_number}] 获取高赞评论失败：{exc}", file=sys.stderr)

            print(f"  [{row_number}] {video_id}  {title}")
            return {**record, "video_id": video_id, "top_comments": top_comments}
        except Exception as exc:
            last_error = exc
            delayed_pages = [
                item
                for item in page.context.pages
                if item not in pages_before and item is not page
            ]
            for delayed_page in delayed_pages:
                if not delayed_page.is_closed():
                    await delayed_page.close()
            if attempt < 3:
                print(f"  [{row_number}] 点击未响应，正在重试（{attempt}/3）")
                await page.wait_for_timeout(500)
        finally:
            if popup and not popup.is_closed():
                await popup.close()

    raise RuntimeError("三次点击后仍未打开详情页") from last_error


async def collect_all_video_details(
    page: Page,
    known_identities: set[VideoIdentity],
    detail_delay: float,
    persist_page: PagePersistor,
    stop_requested: StopRequested,
) -> tuple[int, int, bool]:
    """逐页采集并落盘未出现过的视频，避免跨页累积记录。"""

    collected_count = 0
    skipped_count = 0
    page_number = 1

    while True:
        rows = page.locator("tbody tr")
        await rows.first.wait_for(state="visible", timeout=30_000)
        row_count = await rows.count()
        print(f"\n开始采集第 {page_number} 页，共 {row_count} 条视频：")
        page_records: list[VideoRecord] = []

        for index in range(row_count):
            try:
                row = rows.nth(index)
                list_record = await extract_video_list_record(
                    row=row,
                    page_number=page_number,
                    row_number=index + 1,
                )
                identity = video_identity(
                    list_record["title"], list_record["author_name"]
                )
                if identity in known_identities:
                    skipped_count += 1
                    print(f"  [{index + 1}] 已存在，跳过详情页：{list_record['title']}")
                    continue

                record = await capture_video_detail(
                    page=page,
                    row=row,
                    row_number=index + 1,
                    record=list_record,
                )
                page_records.append(record)
                known_identities.add(identity)
                wait_seconds = (
                    0.0
                    if detail_delay == 0
                    else max(
                        0.0,
                        detail_delay
                        + uniform(-DETAIL_DELAY_JITTER, DETAIL_DELAY_JITTER),
                    )
                )
                if wait_seconds:
                    print(f"  等待 {wait_seconds:.2f} 秒后采集下一条")
                    await page.wait_for_timeout(wait_seconds * 1_000)
            except Exception as exc:
                print(f"  [{index + 1}] 获取 video_id 失败：{exc}", file=sys.stderr)

        if page_records:
            await persist_page(page_records, page_number)
            collected_count += len(page_records)
            page_records.clear()
            gc.collect()

        if stop_requested():
            print("安全停止请求已生效：当前页已写入，停止后续翻页")
            return collected_count, skipped_count, True

        next_button = page.locator(
            ".arco-pagination-item-next, .arco-pagination-next"
        ).first
        if not await next_button.is_visible():
            break

        next_class = await next_button.get_attribute("class") or ""
        aria_disabled = await next_button.get_attribute("aria-disabled")
        if "disabled" in next_class or aria_disabled == "true":
            break

        first_row_text = await rows.first.inner_text()
        await next_button.click()
        try:
            await page.wait_for_function(
                """
                previousText => {
                    const firstRow = document.querySelector('tbody tr');
                    return firstRow && firstRow.innerText !== previousText;
                }
                """,
                arg=first_row_text,
                timeout=30_000,
            )
        except PlaywrightTimeoutError:
            print("等待下一页表格更新超时，停止翻页", file=sys.stderr)
            break

        page_number += 1
        await page.wait_for_timeout(1_000)

    print(f"\n共获取 {collected_count} 个新 video_id，跳过 {skipped_count} 条已有视频")
    return collected_count, skipped_count, False
