"""榜单页面的搜索和筛选交互。"""

import asyncio
import re

from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


async def print_input_candidates(page: Page) -> None:
    """输出当前页面所有可见输入框，便于排查页面结构变化。"""

    inputs = page.locator("input")
    count = await inputs.count()
    print(f"\n页面共发现 {count} 个 input 元素：")

    for index in range(count):
        element = inputs.nth(index)

        try:
            if not await element.is_visible():
                continue

            print(
                f"[input {index}] "
                f"editable={await element.is_editable()}, "
                f"type={await element.get_attribute('type')!r}, "
                f"placeholder={await element.get_attribute('placeholder')!r}, "
                f"aria-label={await element.get_attribute('aria-label')!r}, "
                f"class={await element.get_attribute('class')!r}"
            )
        except Exception:
            continue


async def find_search_input(page: Page) -> Locator:
    """查找最可能的搜索输入框。"""

    selectors = [
        'input[placeholder*="热门搜索"]',
        'input[placeholder*="搜索"]',
        'input[placeholder*="关键词"]',
        'input[aria-label*="搜索"]',
        'input[type="search"]',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        for index in range(await locator.count()):
            candidate = locator.nth(index)

            if await candidate.is_visible() and await candidate.is_editable():
                print(f"自动选中搜索框：{selector}")
                return candidate

    candidates: list[tuple[int, Locator, str]] = []
    all_inputs = page.locator(
        'input:not([type]), input[type="text"], input[type="search"]'
    )

    for index in range(await all_inputs.count()):
        candidate = all_inputs.nth(index)

        try:
            if not await candidate.is_visible() or not await candidate.is_editable():
                continue

            placeholder = await candidate.get_attribute("placeholder") or ""
            aria_label = await candidate.get_attribute("aria-label") or ""
            input_type = await candidate.get_attribute("type") or "text"
            surrounding_text = await candidate.evaluate(
                """
                element => {
                    const parent = element.closest('form')
                        || element.parentElement?.parentElement
                        || element.parentElement;
                    return parent?.innerText || '';
                }
                """
            )
            score = (
                (100 if input_type == "search" else 0)
                + (80 if "搜索" in placeholder else 0)
                + (70 if "关键词" in placeholder else 0)
                + (60 if "搜索" in aria_label else 0)
                + (50 if "热门搜索" in surrounding_text else 0)
            )
            candidates.append(
                (
                    score,
                    candidate,
                    f"type={input_type!r}, placeholder={placeholder!r}, "
                    f"aria-label={aria_label!r}",
                )
            )
        except Exception:
            continue

    if not candidates:
        raise RuntimeError("没有发现可编辑的文本输入框")

    candidates.sort(key=lambda item: item[0], reverse=True)
    score, candidate, description = candidates[0]
    print(f"使用评分最高的输入框：score={score}, {description}")
    return candidate


async def wait_for_search_input(page: Page, timeout_seconds: float) -> Locator:
    """轮询等待异步渲染的搜索输入框变为可编辑状态。"""

    if timeout_seconds <= 0:
        raise ValueError("--input-timeout 必须大于 0")

    deadline = asyncio.get_running_loop().time() + timeout_seconds

    while True:
        try:
            return await find_search_input(page)
        except RuntimeError:
            if asyncio.get_running_loop().time() >= deadline:
                await print_input_candidates(page)
                raise RuntimeError(
                    f"等待 {timeout_seconds:g} 秒后仍未发现可编辑的文本输入框"
                )
            await page.wait_for_timeout(500)


async def submit_search(page: Page, keyword: str, input_timeout: float) -> None:
    """填入关键词并触发搜索。"""

    table_body = page.locator("tbody").first
    before_table = ""

    try:
        if await table_body.is_visible():
            before_table = await table_body.inner_text()
    except Exception:
        pass

    fill_error: Exception | None = None

    for attempt in range(1, 4):
        search_input = await wait_for_search_input(page, input_timeout)

        try:
            await search_input.scroll_into_view_if_needed(timeout=5_000)
            await search_input.click(timeout=5_000)
            await search_input.fill(keyword, timeout=5_000)
            fill_error = None
            break
        except PlaywrightTimeoutError as exc:
            fill_error = exc
            print(f"搜索框在点击前被页面替换，正在重试（{attempt}/3）")

    if fill_error is not None:
        raise RuntimeError("多次重试后仍无法填写搜索框") from fill_error

    print(f"已输入关键词：{keyword}")
    buttons = page.locator("button").filter(
        has_text=re.compile(r"^\s*(搜索|查询)\s*$")
    )

    for index in range(await buttons.count()):
        button = buttons.nth(index)

        if await button.is_visible():
            await button.click()
            print("已点击页面搜索按钮")
            break
    else:
        await search_input.press("Enter")
        print("未发现搜索按钮，已按 Enter")

    if before_table:
        try:
            await page.wait_for_function(
                """
                previousText => {
                    const tbody = document.querySelector('tbody');
                    const currentText = tbody?.innerText.trim() || '';
                    return currentText.length > 0 && currentText !== previousText;
                }
                """,
                arg=before_table,
                timeout=30_000,
            )
            print("搜索结果表格已经更新")
        except PlaywrightTimeoutError:
            print("等待表格变化超时，继续等待网络请求完成")

    await page.wait_for_timeout(5_000)


async def click_filter(page: Page, filter_value: str, filter_name: str) -> None:
    """点击一个结果筛选，并等待表格内容刷新。"""

    options = page.get_by_text(filter_value, exact=True)
    target: Locator | None = None

    for index in range(await options.count()):
        candidate = options.nth(index)

        if await candidate.is_visible():
            target = candidate
            break

    if target is None:
        raise RuntimeError(f"没有发现{filter_name}筛选：{filter_value}")

    table_body = page.locator("tbody").first
    before_table = ""
    try:
        if await table_body.is_visible():
            before_table = await table_body.inner_text()
    except Exception:
        pass

    await target.scroll_into_view_if_needed()
    await target.click()
    print(f"已点击{filter_name}筛选：{filter_value}")

    if before_table:
        try:
            await page.wait_for_function(
                """
                previousText => {
                    const tbody = document.querySelector('tbody');
                    const currentText = tbody?.innerText.trim() || '';
                    return currentText.length > 0 && currentText !== previousText;
                }
                """,
                arg=before_table,
                timeout=30_000,
            )
            print(f"{filter_name}筛选结果表格已经更新")
        except PlaywrightTimeoutError:
            print(f"等待{filter_name}筛选结果变化超时，继续保存当前页面")

    await page.wait_for_timeout(2_000)


async def click_result_type(page: Page, result_type: str) -> None:
    """点击结果类型筛选。"""

    await click_filter(page, result_type, "类型")


async def click_time_range(page: Page, time_range: str) -> None:
    """点击结果时间范围筛选。"""

    await click_filter(page, time_range, "时间")
