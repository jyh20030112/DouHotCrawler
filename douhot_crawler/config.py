"""项目运行常量。"""

from pathlib import Path


TARGET_URL = (
    "https://douhot.douyin.com/square/hotspot"
    "?active_tab=hotspot_video"
    "&date_window=168"
    "&sub_type=1001"
)

DEFAULT_RESULT_TYPE = "低粉爆款"
DEFAULT_TIME_RANGE = "近7天"
DEFAULT_DETAIL_DELAY = 1.0
DETAIL_DELAY_JITTER = 0.2
TIME_RANGE_CHOICES = ("近1小时", "近1天", "近3天", "近7天")

DOUYIN_VIDEO_URL_PREFIX = "https://www.douyin.com/video/"
RESULT_EXCEL_PATH = Path("result") / "result.xlsx"
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
