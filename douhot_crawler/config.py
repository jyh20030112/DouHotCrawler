"""项目运行常量。"""

import os
import sys
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """加载简单的 .env 文件，且不覆盖已设置的系统环境变量。"""
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv(Path.cwd() / ".env")


def _data_dir() -> Path:
    """返回平台相关的用户数据目录。"""
    if sys.platform == "win32":
        base = os.environ.get(
            "LOCALAPPDATA", str(Path.home() / "AppData" / "Local")
        )
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get(
            "XDG_DATA_HOME", str(Path.home() / ".local" / "share")
        )
    return Path(base) / "DouHotCrawler"


TARGET_URL = (
    "https://douhot.douyin.com/square/hotspot"
    "?active_tab=hotspot_video"
    "&date_window=168"
    "&sub_type=1001"
)
LOGIN_URL = "https://douhot.douyin.com/"

DEFAULT_RESULT_TYPE = "低粉爆款"
DEFAULT_TIME_RANGE = "近7天"
DEFAULT_DETAIL_DELAY = 1.0
DETAIL_DELAY_JITTER = 0.2
TIME_RANGE_CHOICES = ("近1小时", "近1天", "近3天", "近7天")

DOUYIN_VIDEO_URL_PREFIX = "https://www.douyin.com/video/"
RESULT_EXCEL_PATH = _data_dir() / "result" / "result.xlsx"
COOKIE_CONFIG_PATH = _data_dir() / "cookie.config"
EXTRACT_API_URL = os.environ.get("EXTRACT_API_URL", "").strip()
RESULT_HEADERS = [
    "序号",
    "类型",
    "爬取到的时间",
    "时间类型",
    "视频名称",
    "视频的url",
    "博主名称",
    "总粉丝数",
    "热度值",
    "新增播放量",
    "新增点赞量",
    "点赞率",
    "高赞评论",
]

PROFILE_PATH = Path.home() / ".crawl4ai" / "profiles" / "douhot"
