"""Douhot 扫码登录命令行入口。"""

import argparse
import asyncio
import sys

from .login import run_login


def main() -> None:
    parser = argparse.ArgumentParser(description="打开 Douhot 扫码登录页面并更新爬虫 Profile")
    parser.parse_args()
    asyncio.run(run_login())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n登录失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
