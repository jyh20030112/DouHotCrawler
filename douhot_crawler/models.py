"""跨模块使用的数据类型。"""

from dataclasses import dataclass
from typing import TypeAlias


VideoRecord: TypeAlias = dict[str, str]
VideoIdentity: TypeAlias = tuple[str, str]


@dataclass(frozen=True)
class RunOptions:
    """一次关键词搜索任务的运行参数。"""

    keyword: str
    input_timeout: float
    detail_delay: float
    result_type: str
    time_range: str
    headless: bool


def video_identity(title: object, author_name: object) -> VideoIdentity:
    """使用视频名称与博主名称标识一条视频。"""

    return str(title).strip(), str(author_name).strip()
