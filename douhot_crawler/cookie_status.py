"""读取 Douhot Chromium Profile 中的登录 Cookie 状态。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import PROFILE_PATH


# Chromium 的 expires_utc 以 1601-01-01 为起点，单位是微秒。
_CHROMIUM_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)
_LOGIN_COOKIE_NAMES = (
    "sessionid_douhot",
    "sessionid_ss_douhot",
    "sid_tt_douhot",
    "sid_guard_douhot",
)
_PRIMARY_LOGIN_COOKIE = "sessionid_douhot"
_EXPIRING_SOON = timedelta(days=7)


@dataclass(frozen=True)
class CookieStatus:
    """供 CLI 或 GUI 展示的、不会包含 Cookie 内容的状态。"""

    state: str
    label: str
    detail: str
    expires_at: datetime | None = None


def _chromium_expiry(value: int) -> datetime | None:
    """把 Chromium 到期时间转换为时区感知的本地时间。"""

    if value <= 0:
        return None
    return (_CHROMIUM_EPOCH + timedelta(microseconds=value)).astimezone()


def _cookie_database(profile_path: Path) -> Path | None:
    """兼容 Chromium Profile 根目录与 Default 子目录两种布局。"""

    for relative_path in (Path("Default") / "Cookies", Path("Cookies")):
        candidate = profile_path / relative_path
        if candidate.is_file():
            return candidate
    return None


def inspect_douhot_cookie(
    profile_path: Path = PROFILE_PATH,
    *,
    now: datetime | None = None,
) -> CookieStatus:
    """检查本地 Profile 的关键 Douhot 登录 Cookie 是否仍在有效期内。

    这项检查只读取 Chromium 的 Cookie 元数据，不会读取或输出 Cookie 值。
    服务端主动注销的状态无法通过本地有效期准确判断。
    """

    cookie_db = _cookie_database(profile_path)
    if cookie_db is None:
        return CookieStatus(
            "missing",
            "Cookie 未找到",
            "未找到 Douhot 浏览器 Profile，请先创建并登录。",
        )

    try:
        connection = sqlite3.connect(f"file:{cookie_db}?mode=ro", uri=True)
        try:
            placeholders = ", ".join("?" for _ in _LOGIN_COOKIE_NAMES)
            rows = connection.execute(
                "SELECT name, expires_utc FROM cookies "
                "WHERE host_key LIKE '%douyin.com%' AND name IN ("
                f"{placeholders})",
                _LOGIN_COOKIE_NAMES,
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return CookieStatus(
            "unknown",
            "Cookie 无法检测",
            f"无法读取浏览器 Cookie 数据库：{exc}。",
        )

    if not rows:
        return CookieStatus(
            "missing",
            "Cookie 未登录",
            "Profile 中没有找到 Douhot 的登录 Cookie，请重新登录。",
        )

    reference_time = now or datetime.now().astimezone()
    expiries_by_name = {
        name: _chromium_expiry(int(expiry)) for name, expiry in rows
    }
    primary_expiry = expiries_by_name.get(_PRIMARY_LOGIN_COOKIE)
    if _PRIMARY_LOGIN_COOKIE not in expiries_by_name:
        return CookieStatus(
            "missing",
            "账号 Cookie 未登录",
            "Profile 中没有找到 Douhot 的主登录 Cookie，请重新登录。",
        )
    if primary_expiry is not None and primary_expiry <= reference_time:
        return CookieStatus(
            "expired",
            "账号 Cookie 已过期",
            "本地 Douhot 登录 Cookie 已过期，请重新登录。",
        )

    # 多个登录 Cookie 的有效期可能不同；以最早的持久 Cookie 到期日提示续期。
    persistent_expiries = [
        expiry
        for expiry in expiries_by_name.values()
        if expiry is not None and expiry > reference_time
    ]
    earliest_expiry = min(persistent_expiries, default=None)
    if earliest_expiry and earliest_expiry - reference_time <= _EXPIRING_SOON:
        return CookieStatus(
            "expiring",
            "账号 Cookie 即将过期",
            f"本地 Cookie 将于 {earliest_expiry:%Y-%m-%d %H:%M} 过期。",
            earliest_expiry,
        )

    if earliest_expiry:
        detail = f"本地 Cookie 有效至 {earliest_expiry:%Y-%m-%d %H:%M}。"
    else:
        detail = "本地会话 Cookie 存在；关闭浏览器后可能失效。"
    return CookieStatus("valid", "账号 Cookie 有效", detail, earliest_expiry)
