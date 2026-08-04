"""读取 Douhot Chromium Profile 中的登录 Cookie 状态。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from douhot_crawler.core.config import PROFILE_PATH


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


def _profile_diagnostics(profile_path: Path) -> str:
    """返回 Profile 目录的诊断信息，用于无法找到 Cookie 时的排查。"""

    lines = [f"Profile 路径：{profile_path}"]
    if not profile_path.is_dir():
        lines.append("该目录不存在。")
        return "\n".join(lines)

    try:
        top = sorted(p.name for p in profile_path.iterdir())
    except OSError:
        top = ["<无法读取>"]
    lines.append(f"  目录内容：{', '.join(top[:15])}")

    default = profile_path / "Default"
    if default.is_dir():
        try:
            def_entries = sorted(p.name for p in default.iterdir())
        except OSError:
            def_entries = ["<无法读取>"]
        lines.append(f"  Default 内容：{', '.join(def_entries[:15])}")

    cookies_paths = [
        profile_path / "Default" / "Network" / "Cookies",
        profile_path / "Default" / "Cookies",
        profile_path / "Cookies",
    ]
    for p in cookies_paths:
        label = str(p.relative_to(profile_path))
        lines.append(f"  {label}: {'存在' if p.is_file() else '不存在'}")
    return "\n".join(lines)


def _cookie_database(profile_path: Path) -> Path | None:
    """兼容各版本 Chromium 的 Cookie 数据库路径布局。

    Chrome/Edge 100+ 将 Cookies 移至 Default/Network/ 子目录。
    """

    for relative_path in (
        Path("Default") / "Network" / "Cookies",  # Chrome/Edge ≥100
        Path("Default") / "Cookies",               # 旧版本
        Path("Cookies"),                            # 非 Default Profile
    ):
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
        diag = _profile_diagnostics(profile_path)
        return CookieStatus(
            "missing",
            "Cookie 未找到",
            f"未找到 Douhot 浏览器 Profile 的 Cookies 文件。\n{diag}",
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
            f"无法读取浏览器 Cookie 数据库：{exc}。\n数据库路径：{cookie_db}",
        )

    if not rows:
        # 列出数据库中所有 douyin 相关 cookie 名称，帮助排查名称不匹配
        try:
            connection = sqlite3.connect(f"file:{cookie_db}?mode=ro", uri=True)
            try:
                all_douyin = connection.execute(
                    "SELECT DISTINCT name FROM cookies "
                    "WHERE host_key LIKE '%douyin.com%'"
                ).fetchall()
            finally:
                connection.close()
            existing_names = [r[0] for r in all_douyin]
        except sqlite3.Error:
            existing_names = ["<读取失败>"]

        return CookieStatus(
            "missing",
            "Cookie 未登录",
            f"Cookie 数据库中没有找到预期的 Douhot 登录 Cookie。\n"
            f"数据库路径：{cookie_db}\n"
            f"期望的 Cookie：{', '.join(_LOGIN_COOKIE_NAMES)}\n"
            f"实际 douyin 相关 Cookie：{', '.join(existing_names[:20])}",
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
