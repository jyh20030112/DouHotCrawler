"""视频详情页评论采集。"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


def comment_analysis_url(detail_url: str) -> str:
    """将视频详情 URL 切换为评论分析页。"""

    parts = urlsplit(detail_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["active_tab"] = "video_comment"
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


async def fetch_top_comments(page: Page) -> str:
    """进入评论分析页，提取点赞最高的前四条评论。"""

    await page.goto(
        comment_analysis_url(page.url),
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    comments = page.locator("div[class*='comment___']")

    try:
        await comments.first.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError:
        print("  评论分析页没有可见评论")
        return ""

    comment_data = await comments.evaluate_all(
        """
        elements => elements.slice(0, 4).map(comment => {
            const container = comment.parentElement;
            const nickname = container?.querySelector("[class*='nickname___']")
                ?.innerText.trim() || '';
            const likeCount = container?.querySelector("[class*='like___'] [class*='count___']")
                ?.innerText.trim() || '0';
            const content = comment.innerText.trim();
            return { nickname, likeCount, content };
        })
        """
    )

    return " / ".join(
        f"{item['nickname']}（{item['likeCount']}赞）：{item['content']}"
        for item in comment_data
        if item["nickname"] or item["content"]
    )
