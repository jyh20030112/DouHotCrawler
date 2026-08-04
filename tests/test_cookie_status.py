import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from douhot_crawler.browser.cookies import inspect_douhot_cookie
from douhot_crawler.browser.login import _login_run_config
from douhot_crawler.transcript.cookies import (
    inspect_transcript_cookie,
    save_transcript_cookie,
)


CHROMIUM_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)


def chromium_timestamp(value: datetime) -> int:
    return int((value - CHROMIUM_EPOCH).total_seconds() * 1_000_000)


class CookieStatusTests(unittest.TestCase):
    def create_profile(
        self, expires_utc: int | None, extra_cookies: tuple[tuple[str, int], ...] = ()
    ) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        profile = Path(temp_dir.name)
        database = profile / "Default" / "Cookies"
        database.parent.mkdir()
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE cookies (host_key TEXT, name TEXT, expires_utc INTEGER)"
            )
            if expires_utc is not None:
                connection.execute(
                    "INSERT INTO cookies VALUES (?, ?, ?)",
                    (".douhot.douyin.com", "sessionid_douhot", expires_utc),
                )
            connection.executemany(
                "INSERT INTO cookies VALUES (?, ?, ?)",
                [
                    (".douhot.douyin.com", name, expiry)
                    for name, expiry in extra_cookies
                ],
            )
        return profile

    def test_missing_cookie_database(self) -> None:
        status = inspect_douhot_cookie(Path("/not/a/profile"))
        self.assertEqual(status.state, "missing")

    def test_expired_cookie(self) -> None:
        now = datetime(2026, 7, 23, tzinfo=UTC)
        profile = self.create_profile(chromium_timestamp(now - timedelta(minutes=1)))
        status = inspect_douhot_cookie(profile, now=now)
        self.assertEqual(status.state, "expired")

    def test_cookie_expiring_soon(self) -> None:
        now = datetime(2026, 7, 23, tzinfo=UTC)
        profile = self.create_profile(chromium_timestamp(now + timedelta(days=2)))
        status = inspect_douhot_cookie(profile, now=now)
        self.assertEqual(status.state, "expiring")

    def test_valid_cookie(self) -> None:
        now = datetime(2026, 7, 23, tzinfo=UTC)
        profile = self.create_profile(chromium_timestamp(now + timedelta(days=8)))
        status = inspect_douhot_cookie(profile, now=now)
        self.assertEqual(status.state, "valid")

    def test_expired_primary_cookie_is_not_masked_by_other_cookie(self) -> None:
        now = datetime(2026, 7, 23, tzinfo=UTC)
        profile = self.create_profile(
            chromium_timestamp(now - timedelta(minutes=1)),
            (("sid_guard_douhot", chromium_timestamp(now + timedelta(days=30))),),
        )
        status = inspect_douhot_cookie(profile, now=now)
        self.assertEqual(status.state, "expired")

    def test_login_page_uses_a_persistent_crawler_session(self) -> None:
        self.assertEqual(_login_run_config().session_id, "douhot-login")

    def test_transcript_cookie_expiry_comes_from_sid_guard(self) -> None:
        now = datetime(2026, 7, 23, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temporary_directory:
            cookie_path = Path(temporary_directory) / "cookie.config"
            cookie_path.write_text(
                "sessionid=redacted; sid_guard=redacted%7C1700000000%7C3600%7Cfoo",
                encoding="utf-8",
            )
            status = inspect_transcript_cookie(cookie_path, now=now)
        self.assertEqual(status.state, "expired")

    def test_transcript_cookie_without_expiry_is_reported_honestly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cookie_path = Path(temporary_directory) / "cookie.config"
            cookie_path.write_text("sessionid=redacted", encoding="utf-8")
            status = inspect_transcript_cookie(cookie_path)
        self.assertEqual(status.state, "unknown")

    def test_transcript_cookie_save_replaces_the_target_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cookie_path = Path(temporary_directory) / "cookie.config"
            save_transcript_cookie("sessionid=redacted; sid_guard=redacted", cookie_path)
            saved = cookie_path.read_text(encoding="utf-8")
        self.assertEqual(saved, "sessionid=redacted; sid_guard=redacted\n")


if __name__ == "__main__":
    unittest.main()
