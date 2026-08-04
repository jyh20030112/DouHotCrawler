"""检测并安全更新口播提取使用的抖音 Cookie。"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

from douhot_crawler.browser.cookies import CookieStatus
from douhot_crawler.core.config import COOKIE_CONFIG_PATH


DEFAULT_TRANSCRIPT_COOKIE_PATH = COOKIE_CONFIG_PATH
_EXPIRING_SOON = timedelta(days=7)


def _cookie_values(cookie: str) -> dict[str, str]:
    """解析浏览器复制的 Cookie 请求头，忽略无法识别的片段。"""

    values: dict[str, str] = {}
    for fragment in cookie.replace("\n", ";").split(";"):
        if "=" not in fragment:
            continue
        name, value = fragment.strip().split("=", 1)
        if name:
            values[name.strip()] = value.strip()
    return values


def _sid_guard_expiry(value: str) -> datetime | None:
    """从 sid_guard 的 `session|issued_at|ttl|...` 编码中取出本地到期时间。"""

    parts = unquote(value).split("|")
    for index in range(len(parts) - 1):
        try:
            issued_at = int(parts[index])
            ttl = int(parts[index + 1])
        except ValueError:
            continue
        # Unix 秒级时间戳和合理的有效期范围，避免把随机数字误作日期。
        if 946_684_800 <= issued_at <= 4_102_444_800 and 60 <= ttl <= 315_360_000:
            return datetime.fromtimestamp(issued_at + ttl).astimezone()
    return None


def inspect_transcript_cookie(
    cookie_path: Path = DEFAULT_TRANSCRIPT_COOKIE_PATH,
    *,
    now: datetime | None = None,
) -> CookieStatus:
    """检查 `cookie.config` 中用于 www.douyin.com 的登录 Cookie。"""

    if not cookie_path.is_file():
        return CookieStatus(
            "missing",
            "口播 Cookie 未找到",
            "没有找到 cookie.config，请粘贴 www.douyin.com 的 Cookie 后保存。",
        )

    cookie = cookie_path.read_text(encoding="utf-8").strip()
    if not cookie:
        return CookieStatus(
            "missing",
            "口播 Cookie 为空",
            "cookie.config 为空，请粘贴 www.douyin.com 的 Cookie 后保存。",
        )

    values = _cookie_values(cookie)
    if not values.get("sessionid"):
        return CookieStatus(
            "missing",
            "口播 Cookie 未登录",
            "未发现 sessionid，请在 www.douyin.com 登录后重新复制 Cookie。",
        )

    expiry = _sid_guard_expiry(values.get("sid_guard", ""))
    if expiry is None:
        return CookieStatus(
            "unknown",
            "口播 Cookie 已配置",
            "已发现 sessionid，但无法从 sid_guard 判断到期时间；请以实际提取结果为准。",
        )

    reference_time = now or datetime.now().astimezone()
    if expiry <= reference_time:
        return CookieStatus(
            "expired",
            "口播 Cookie 已过期",
            "请登录 www.douyin.com，复制新 Cookie 并在此页手动保存。",
            expiry,
        )
    if expiry - reference_time <= _EXPIRING_SOON:
        return CookieStatus(
            "expiring",
            "口播 Cookie 即将过期",
            f"本地 Cookie 将于 {expiry:%Y-%m-%d %H:%M} 过期，请及时更新。",
            expiry,
        )
    return CookieStatus(
        "valid",
        "口播 Cookie 有效",
        f"本地 Cookie 有效至 {expiry:%Y-%m-%d %H:%M}。",
        expiry,
    )


def save_transcript_cookie(
    cookie: str, cookie_path: Path = DEFAULT_TRANSCRIPT_COOKIE_PATH
) -> None:
    """原子替换 Cookie 文件，避免中途退出留下半截凭据。"""

    cleaned = cookie.strip()
    if not cleaned:
        raise ValueError("Cookie 不能为空")
    if not _cookie_values(cleaned).get("sessionid"):
        raise ValueError("Cookie 中未发现 sessionid，请确认复制的是 www.douyin.com 的完整 Cookie")

    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{cookie_path.name}.", suffix=".tmp", dir=cookie_path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(cleaned + "\n")
        os.replace(temporary_path, cookie_path)
    except Exception:
        Path(temporary_path).unlink(missing_ok=True)
        raise
