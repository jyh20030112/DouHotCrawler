"""Fluent 设置界面。"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QLabel, QWidget
from qfluentwidgets import (
    ComboBoxSettingCard,
    ExpandLayout,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    PushSettingCard,
    ScrollArea,
    SettingCardGroup,
    SwitchSettingCard,
    setFont,
)

from douhot_crawler.core.config import PROFILE_PATH, RESULT_EXCEL_PATH

from .config import CONFIG_FILE, cfg, is_windows_11


try:
    APP_VERSION = version("crael4i-demo")
except PackageNotFoundError:
    APP_VERSION = "0.1.0"


class SettingsInterface(ScrollArea):
    """管理界面外观、本地数据位置和应用信息。"""

    mica_enable_changed = Signal(bool)
    open_log_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)
        self.scroll_widget = QWidget()
        self.expand_layout = ExpandLayout(self.scroll_widget)
        self.title_label = QLabel("设置", self)

        self.personal_group = SettingCardGroup("个性化", self.scroll_widget)
        self.mica_card = SwitchSettingCard(
            FIF.TRANSPARENT,
            "Mica 窗口效果",
            "为标题栏和导航区域启用 Windows 半透明材质。",
            cfg.mica_enabled,
            self.personal_group,
        )
        self.theme_card = ComboBoxSettingCard(
            cfg.themeMode,
            FIF.BRUSH,
            "应用主题",
            "切换工作台的整体明暗外观。",
            texts=["浅色", "深色", "跟随系统"],
            parent=self.personal_group,
        )
        self.zoom_card = ComboBoxSettingCard(
            cfg.dpi_scale,
            FIF.ZOOM,
            "界面缩放",
            "调整控件与字体大小，重启应用后生效。",
            texts=["100%", "125%", "150%", "175%", "200%", "跟随系统"],
            parent=self.personal_group,
        )

        self.storage_group = SettingCardGroup("数据与存储", self.scroll_widget)
        self.result_card = PushSettingCard(
            "打开",
            FIF.FOLDER,
            "结果目录",
            str(RESULT_EXCEL_PATH.parent.resolve()),
            self.storage_group,
        )
        self.profile_card = PushSettingCard(
            "打开",
            FIF.PEOPLE,
            "浏览器 Profile",
            str(PROFILE_PATH),
            self.storage_group,
        )
        self.config_card = PushSettingCard(
            "打开",
            FIF.SETTING,
            "应用配置",
            str(CONFIG_FILE),
            self.storage_group,
        )

        self.application_group = SettingCardGroup("应用", self.scroll_widget)
        self.log_card = PushSettingCard(
            "查看",
            FIF.COMMAND_PROMPT,
            "运行日志",
            "查看当前任务状态、实时输出和安全停止操作。",
            self.application_group,
        )
        self.about_card = PushSettingCard(
            "查看说明",
            FIF.INFO,
            "Douhot 数据工作台",
            f"版本 {APP_VERSION} · 热榜采集、Excel 归档与口播提取",
            self.application_group,
        )

        self._init_widget()
        self._init_layout()
        self._connect_signals()

    def _init_widget(self) -> None:
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 82, 0, 20)
        self.setWidget(self.scroll_widget)
        self.setWidgetResizable(True)
        self.setObjectName("settingsInterface")
        self.scroll_widget.setObjectName("settingsScrollWidget")
        self.title_label.setObjectName("settingsTitle")
        self.scroll_widget.setStyleSheet("QWidget { background: transparent; }")
        setFont(self.title_label, 24, QFont.Weight.DemiBold)
        self.title_label.move(32, 30)
        self.mica_card.setEnabled(is_windows_11())

    def _init_layout(self) -> None:
        self.personal_group.addSettingCard(self.mica_card)
        self.personal_group.addSettingCard(self.theme_card)
        self.personal_group.addSettingCard(self.zoom_card)
        self.storage_group.addSettingCard(self.result_card)
        self.storage_group.addSettingCard(self.profile_card)
        self.storage_group.addSettingCard(self.config_card)
        self.application_group.addSettingCard(self.log_card)
        self.application_group.addSettingCard(self.about_card)

        self.expand_layout.setSpacing(24)
        self.expand_layout.setContentsMargins(32, 8, 32, 24)
        self.expand_layout.addWidget(self.personal_group)
        self.expand_layout.addWidget(self.storage_group)
        self.expand_layout.addWidget(self.application_group)

    def _connect_signals(self) -> None:
        self.mica_card.checkedChanged.connect(self.mica_enable_changed)
        self.result_card.clicked.connect(
            lambda: self._open_directory(RESULT_EXCEL_PATH.parent)
        )
        self.profile_card.clicked.connect(lambda: self._open_directory(PROFILE_PATH))
        self.config_card.clicked.connect(
            lambda: self._open_directory(CONFIG_FILE.parent)
        )
        self.log_card.clicked.connect(self.open_log_requested)
        self.about_card.clicked.connect(self._open_readme)
        cfg.appRestartSig.connect(self._show_restart_message)

    def _open_directory(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            InfoBar.error("无法打开目录", str(exc), parent=self)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    @staticmethod
    def _open_readme() -> None:
        readme = RESULT_EXCEL_PATH.resolve().parents[1] / "README.md"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(readme)))

    def _show_restart_message(self) -> None:
        InfoBar.success(
            title="设置已保存",
            content="界面缩放将在重启应用后生效。",
            duration=2_500,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self,
        )
