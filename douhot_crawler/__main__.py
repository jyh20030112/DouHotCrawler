"""抖音热榜爬虫的命令行入口。"""

import asyncio
import sys

from .crawling.runner import run
from .interfaces.crawl_cli import parse_args


def main() -> None:
    """解析命令行参数并启动异步任务。"""

    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
