"""桌面界面的持久化外观配置。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from qfluentwidgets import (
    BoolValidator,
    ConfigItem,
    OptionsConfigItem,
    OptionsValidator,
    QConfig,
    Theme,
    qconfig,
)


def is_windows_11() -> bool:
    return (
        sys.platform == "win32"
        and hasattr(sys, "getwindowsversion")
        and sys.getwindowsversion().build >= 22_000
    )


def _config_directory() -> Path:
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "DouHotCrawler"
    return Path.home() / ".config" / "DouHotCrawler"


CONFIG_FILE = _config_directory() / "config.json"


class UiConfig(QConfig):
    """从参考 Fluent 项目迁移的窗口配置。"""

    mica_enabled = ConfigItem(
        "MainWindow", "MicaEnabled", is_windows_11(), BoolValidator()
    )
    dpi_scale = OptionsConfigItem(
        "MainWindow",
        "DpiScale",
        "Auto",
        OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]),
        restart=True,
    )


cfg = UiConfig()
cfg.themeMode.value = Theme.AUTO
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
qconfig.load(str(CONFIG_FILE), cfg)
