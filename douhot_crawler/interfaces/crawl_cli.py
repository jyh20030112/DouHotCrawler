"""命令行参数解析。"""

import argparse

from douhot_crawler.core.config import (
    DEFAULT_RESULT_TYPE,
    DEFAULT_TIME_RANGE,
    DEFAULT_DETAIL_DELAY,
    TIME_RANGE_CHOICES,
)
from douhot_crawler.core.models import RunOptions


def parse_args() -> RunOptions:
    """解析并返回一次爬取任务的参数。"""

    parser = argparse.ArgumentParser(
        description="使用 douhot Profile 搜索热门关键词并爬取结果"
    )
    parser.add_argument(
        "keyword",
        help='热门搜索关键词，例如 "大健康"',
    )
    parser.add_argument(
        "--input-timeout",
        type=float,
        default=30.0,
        help="等待搜索输入框出现的最长秒数（默认：30）",
    )
    parser.add_argument(
        "--detail-delay",
        type=float,
        default=DEFAULT_DETAIL_DELAY,
        help="每条新视频详情采集后的基础等待秒数（默认：1）",
    )
    parser.add_argument(
        "--result-type",
        default=DEFAULT_RESULT_TYPE,
        help=f"搜索后点击的类型筛选（默认：{DEFAULT_RESULT_TYPE}）",
    )
    parser.add_argument(
        "--time-range",
        choices=TIME_RANGE_CHOICES,
        default=DEFAULT_TIME_RANGE,
        help=f"搜索后点击的时间筛选（默认：{DEFAULT_TIME_RANGE}）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式运行；首次调试不要添加",
    )
    args = parser.parse_args()

    return RunOptions(
        keyword=args.keyword,
        input_timeout=args.input_timeout,
        detail_delay=args.detail_delay,
        result_type=args.result_type,
        time_range=args.time_range,
        headless=args.headless,
    )
