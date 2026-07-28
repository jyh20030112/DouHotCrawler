"""Douhot 爬取与口播提取的 Qt 桌面图形界面。"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import os
import signal
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (QEvent, QLocale, QObject, QStandardPaths, Qt,
                            QThread, QTimer, Signal, Slot)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon
from PySide6.QtWidgets import (QApplication, QFileDialog, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLayout, QSizePolicy,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, CheckBox,
                            ComboBox, FluentTranslator, FluentWindow,
                            MessageBox, NavigationItemPosition, ScrollArea)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (InfoBar, InfoBarPosition, LineEdit, PlainTextEdit,
                            PrimaryPushButton, PushButton, SpinBox,
                            SubtitleLabel, TextEdit, Theme, TitleLabel,
                            isDarkTheme, setFont, setTheme, setThemeColor)

from douhot_crawler.cookie_status import CookieStatus, inspect_douhot_cookie
from douhot_crawler.analyzer import (DEFAULT_COOKIE_PATH, DEFAULT_EXCEL_PATH,
                                     analyze_excel)
from douhot_crawler.app import run as run_crawler
from douhot_crawler.browser_setup import chromium_status, install_chromium
from douhot_crawler.config import RESULT_EXCEL_PATH
from douhot_crawler.login import run_login
from douhot_crawler.models import RunOptions
from douhot_crawler.settings_interface import (
    SettingsInterface,
    cfg,
    is_windows_11,
)
from douhot_crawler.transcript_cookie_status import (inspect_transcript_cookie,
                                                     save_transcript_cookie)

# KDE/Wayland 下 Qt 应使用内置的 Wayland text-input 协议，并由 KWin 转交
# 给 Fcitx。系统全局 QT_IM_MODULE=fcitx 会要求 PySide6 加载 ABI 不兼容的
# 系统插件，进而回退为 compose；因此只对本 GUI 进程清除该变量。
# 必须在创建 QApplication 前执行。
os.environ.pop("QT_IM_MODULE", None)


RESULT_TYPES = ("低粉爆款", "视频总榜", "高完播率", "高涨粉率", "高点赞率")
TIME_RANGES = ("近1小时", "近1天", "近3天", "近7天")
APP_ICON_PATH = Path(__file__).resolve().parent / "resources" / "favicon.ico"

APP_STYLESHEET = """
QWidget#pageContent {
    background: transparent;
}
QScrollArea#taskScrollArea,
QScrollArea#taskScrollArea > QWidget > QWidget {
    background: transparent; border: 0;
}
QScrollArea#settingsInterface,
QScrollArea#settingsInterface > QWidget > QWidget,
QWidget#settingsScrollWidget {
    border: 0;
}
"""


class CookieCheckWorker(QObject):
    """在工作线程中读取 Chromium Cookie 数据库，避免启动界面时阻塞。"""

    completed = Signal(object)
    finished = Signal()

    @Slot()
    def check(self) -> None:
        self.completed.emit(inspect_douhot_cookie())
        self.finished.emit()


class BrowserWorker(QObject):
    """在后台检查或下载 Chromium，避免阻塞图形界面。"""

    output = Signal(str)
    completed = Signal(bool, str)
    finished = Signal()

    def __init__(self, *, install: bool = False) -> None:
        super().__init__()
        self.install = install

    @Slot()
    def run(self) -> None:
        try:
            if self.install:
                install_chromium(self.output.emit)
            self.completed.emit(*chromium_status())
        except Exception as exc:
            self.completed.emit(False, str(exc))
        finally:
            self.finished.emit()


class _GuiLogStream(io.TextIOBase):
    """把工作线程中的标准输出安全地转发到 Qt 日志控件。"""

    def __init__(self, signal: Signal) -> None:
        self._signal = signal

    def write(self, text: str) -> int:
        if text:
            self._signal.emit(text)
        return len(text)

    def flush(self) -> None:
        return None


class TaskWorker(QObject):
    """在同一冻结程序中运行任务，避免依赖外部 Python 解释器。"""

    output = Signal(str)
    completed = Signal(bool, str)
    finished = Signal()

    def __init__(self, task_kind: str, payload: object) -> None:
        super().__init__()
        self.task_kind = task_kind
        self.payload = payload
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    @Slot()
    def run(self) -> None:
        stream = _GuiLogStream(self.output)
        try:
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                if self.task_kind == "crawl":
                    asyncio.run(
                        run_crawler(
                            self.payload,  # type: ignore[arg-type]
                            stop_requested=self._stop_event.is_set,
                        )
                    )
                elif self.task_kind == "analyze":
                    analyze_excel(
                        self.payload,  # type: ignore[arg-type]
                        stop_requested=self._stop_event.is_set,
                    )
                elif self.task_kind == "login":
                    asyncio.run(run_login(stop_requested=self._stop_event.is_set))
                else:
                    raise ValueError(f"未知任务类型：{self.task_kind}")
        except Exception as exc:
            self.output.emit(f"\n任务失败：{exc}\n")
            self.completed.emit(False, str(exc))
        else:
            self.completed.emit(True, "")
        finally:
            self.finished.emit()


class AdaptivePushButton(PushButton):
    """在空间不足时自动缩小按钮文字，避免图标或文字被裁切。"""

    minimum_text_size = 8.0

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._base_font = QFont(self.font())
        self._fit_text()

    def setText(self, text: str) -> None:  # type: ignore[override]
        super().setText(text)
        if hasattr(self, "_base_font"):
            self._fit_text()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._fit_text()

    def _fit_text(self) -> None:
        if not self.text():
            return
        font = QFont(self._base_font)
        # Fluent 按钮的图标在左侧绘制，预留图标与左右边距的空间。
        icon_width = 30 if not self.icon().isNull() else 0
        available_width = max(1, self.contentsRect().width() - icon_width - 26)
        if font.pointSizeF() > 0:
            while (
                QFontMetrics(font).horizontalAdvance(self.text()) > available_width
                and font.pointSizeF() > self.minimum_text_size
            ):
                font.setPointSizeF(font.pointSizeF() - 0.5)
        else:
            if font.pixelSize() <= 0:
                return
            while (
                QFontMetrics(font).horizontalAdvance(self.text()) > available_width
                and font.pixelSize() > self.minimum_text_size
            ):
                font.setPixelSize(font.pixelSize() - 1)
        self.setFont(font)


class AdaptivePrimaryPushButton(PrimaryPushButton):
    """主操作按钮的自适应文字版本。"""

    minimum_text_size = 8.0

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._base_font = QFont(self.font())
        self._fit_text()

    def setText(self, text: str) -> None:  # type: ignore[override]
        super().setText(text)
        if hasattr(self, "_base_font"):
            self._fit_text()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._fit_text()

    def _fit_text(self) -> None:
        if not self.text():
            return
        font = QFont(self._base_font)
        icon_width = 30 if not self.icon().isNull() else 0
        available_width = max(1, self.contentsRect().width() - icon_width - 26)
        if font.pointSizeF() > 0:
            while (
                QFontMetrics(font).horizontalAdvance(self.text()) > available_width
                and font.pointSizeF() > self.minimum_text_size
            ):
                font.setPointSizeF(font.pointSizeF() - 0.5)
        else:
            if font.pixelSize() <= 0:
                return
            while (
                QFontMetrics(font).horizontalAdvance(self.text()) > available_width
                and font.pixelSize() > self.minimum_text_size
            ):
                font.setPixelSize(font.pixelSize() - 1)
        self.setFont(font)


class DouhotGui(FluentWindow):
    """使用 Fluent 导航组织采集、口播和日志工作区。"""

    def __init__(self) -> None:
        super().__init__()
        self._task_thread: QThread | None = None
        self._task_worker: TaskWorker | None = None
        self._task_kind: str | None = None
        self._cookie_thread: QThread | None = None
        self._cookie_worker: CookieCheckWorker | None = None
        self._browser_thread: QThread | None = None
        self._browser_worker: BrowserWorker | None = None
        self._browser_ready = False
        self._browser_prompted = False
        self._browser_status_state: str | None = None
        self._crawler_cookie_status: CookieStatus | None = None
        self._transcript_cookie_status: CookieStatus | None = None
        self._centered_on_startup = False
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setWindowTitle("Douhot 数据工作台")
        self.setMinimumSize(780, 620)
        self.setCustomBackgroundColor(QColor(245, 247, 250), QColor(32, 32, 32))
        self.setMicaEffectEnabled(
            is_windows_11() and bool(cfg.get(cfg.mica_enabled))
        )
        self._resize_for_screen()
        self._build_ui()
        cfg.themeChanged.connect(self._change_theme)
        self._apply_workspace_theme()
        self._set_status("就绪 · 等待开始", "#38bdf8")
        self._check_browser()
        self._refresh_crawler_cookie_status()
        self._refresh_transcript_cookie_status()
        self.crawler_cookie_timer = QTimer(self)
        self.crawler_cookie_timer.setInterval(5 * 60 * 1000)
        self.crawler_cookie_timer.timeout.connect(self._refresh_crawler_cookie_status)
        self.crawler_cookie_timer.start()

    def _show_message(self, title: str, content: str) -> None:
        dialog = MessageBox(title, content, self)
        dialog.yesButton.setText("确定")
        dialog.hideCancelButton()
        dialog.exec()

    def _confirm(
        self,
        title: str,
        content: str,
        *,
        confirm_text: str = "确定",
        cancel_text: str = "取消",
    ) -> bool:
        dialog = MessageBox(title, content, self)
        dialog.yesButton.setText(confirm_text)
        dialog.cancelButton.setText(cancel_text)
        return bool(dialog.exec())

    def _build_ui(self) -> None:
        self.crawl_interface = self._workspace(
            "热榜采集",
            "按关键词采集 Douhot 热榜，逐页保存到 Excel 结果库。",
            self._build_crawl_tab(),
            "crawlInterface",
        )
        self.analyze_interface = self._workspace(
            "口播提取",
            "为结果库中的视频补全口播文本，支持分批处理和断点续跑。",
            self._build_analyze_tab(),
            "analyzeInterface",
        )
        self.log_interface = self._build_log_interface()
        self.settings_interface = SettingsInterface(self)
        self.settings_interface.mica_enable_changed.connect(
            self._set_mica_enabled
        )
        self.settings_interface.open_log_requested.connect(
            lambda: self.switchTo(self.log_interface)
        )

        self.addSubInterface(self.crawl_interface, FIF.SEARCH, "热榜采集")
        self.addSubInterface(self.analyze_interface, FIF.VIDEO, "口播提取")
        self.addSubInterface(self.log_interface, FIF.COMMAND_PROMPT, "运行日志")
        self.addSubInterface(
            self.settings_interface,
            FIF.SETTING,
            "设置",
            NavigationItemPosition.BOTTOM,
        )
        self.navigationInterface.setExpandWidth(210)
        self.navigationInterface.setMinimumExpandWidth(900)

    def _change_theme(self, theme) -> None:
        setTheme(theme)
        QTimer.singleShot(0, self._apply_workspace_theme)

    def _apply_workspace_theme(self) -> None:
        dark = isDarkTheme()
        background = "#202020" if dark else "#f5f7fa"
        secondary = "#9a9a9a" if dark else "#60656f"
        status_background = "rgba(46, 46, 46, 210)" if dark else "#ffffff"
        status_border = (
            "rgba(255, 255, 255, 24)" if dark else "rgba(0, 0, 0, 24)"
        )
        title_color = "#ffffff" if dark else "#202020"
        self.setStyleSheet(
            APP_STYLESHEET
            + f"""
            QWidget#crawlInterface, QWidget#analyzeInterface,
            QWidget#logInterface, QScrollArea#settingsInterface,
            QScrollArea#settingsInterface > QWidget > QWidget,
            QWidget#settingsScrollWidget {{ background: {background}; }}
            QLabel#pageSubtitle {{ color: {secondary}; }}
            QLabel#settingsTitle {{ color: {title_color}; background: transparent; }}
            QFrame#statusStrip {{
                background: {status_background};
                border: 1px solid {status_border};
                border-radius: 8px;
            }}
            """
        )
        if self._crawler_cookie_status is not None:
            self.crawler_cookie_badge.setStyleSheet(
                self._cookie_badge_style(self._crawler_cookie_status)
            )
        if self._browser_status_state is not None:
            self.browser_badge.setStyleSheet(
                self._cookie_badge_style(self._browser_status_state)
            )
        if self._transcript_cookie_status is not None:
            self.transcript_cookie_badge.setStyleSheet(
                self._cookie_badge_style(self._transcript_cookie_status)
            )
        self._apply_window_shell_theme()

    def _normalBackgroundColor(self) -> QColor:
        """返回与当前主题一致的窗口底色，避免 Mica 透明层显示成浅色。"""

        if isDarkTheme():
            return QColor(24, 24, 24, 238 if self.isMicaEffectEnabled() else 255)
        return QColor(245, 247, 250, 232 if self.isMicaEffectEnabled() else 255)

    def _apply_window_shell_theme(self) -> None:
        """为标题栏和导航添加主题底色，避免 Mica 返回错误的明暗材质。"""

        self.setBackgroundColor(self._normalBackgroundColor())

    def _set_mica_enabled(self, enabled: bool) -> None:
        self.setMicaEffectEnabled(is_windows_11() and enabled)
        QTimer.singleShot(0, self._apply_window_shell_theme)

    def _build_log_interface(self) -> QWidget:
        page = QWidget()
        page.setObjectName("logInterface")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(16)

        heading = QHBoxLayout()
        title_layout = self._page_heading(
            "运行日志", "集中查看任务进度，并在这里安全停止或导出结果。"
        )
        heading.addLayout(title_layout, 1)
        self.download_excel_button = AdaptivePushButton(FIF.DOWNLOAD, "导出 Excel")
        self.download_excel_button.setMinimumWidth(118)
        self.download_excel_button.clicked.connect(self.download_excel)
        heading.addWidget(self.download_excel_button)
        outer.addLayout(heading)
        outer.addWidget(self._build_status())

        self.log = PlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(280)
        self.log.setMaximumBlockCount(1600)
        self.log.setPlaceholderText("任务启动后的实时输出会显示在这里。")
        outer.addWidget(self.log, 1)
        return page

    def _workspace(
        self,
        title: str,
        subtitle: str,
        content: QWidget,
        object_name: str,
    ) -> QWidget:
        page = QWidget()
        page.setObjectName(object_name)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        layout.addLayout(self._page_heading(title, subtitle))
        layout.addWidget(self._scrollable(content), 1)
        return page

    @staticmethod
    def _page_heading(title: str, subtitle: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.addWidget(TitleLabel(title))
        detail = BodyLabel(subtitle)
        detail.setObjectName("pageSubtitle")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        return layout

    def _resize_for_screen(self) -> None:
        """设置不超过桌面工作区的初始窗口尺寸。"""

        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1100, 880)
            return
        available = screen.availableGeometry()
        self.resize(
            min(1180, max(self.minimumWidth(), available.width() - 140)),
            min(900, max(self.minimumHeight(), available.height() - 80)),
        )

    @staticmethod
    def _scrollable(page: QWidget) -> ScrollArea:
        """小窗口中保持控件自然高度，通过滚动访问后续内容。"""

        scroll = ScrollArea()
        scroll.setObjectName("taskScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        scroll.enableTransparentBackground()
        return scroll

    def _build_crawl_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("pageContent")
        page_layout = QVBoxLayout(page)
        page_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(14)
        readiness_layout = QHBoxLayout()
        readiness_layout.setContentsMargins(0, 0, 0, 0)
        readiness_layout.setSpacing(14)
        readiness_layout.addWidget(self._build_browser_card(), 1)
        readiness_layout.addWidget(self._build_crawler_cookie_card(), 1)
        page_layout.addLayout(readiness_layout)
        card = self._card("创建热榜采集任务", "")
        card.layout().setContentsMargins(26, 32, 26, 32)
        card.layout().setSpacing(14)
        form_container = QWidget()
        form_container.setObjectName("crawlFormContainer")
        form_container.setFixedWidth(600)
        form = QFormLayout(form_container)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(18)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.keyword = LineEdit()
        self.keyword.setPlaceholderText("请输入关键词")
        self.result_type = ComboBox()
        self.result_type.addItems(RESULT_TYPES)
        self.time_range = ComboBox()
        self.time_range.addItems(TIME_RANGES)
        self.time_range.setCurrentText("近7天")
        self.input_timeout = self._spin(1, 300, 30)
        self.detail_delay = self._spin(0, 60, 1)
        self.headless = CheckBox("无头模式")
        self.crawl_button = AdaptivePrimaryPushButton(
            FIF.SEARCH.icon(Theme.LIGHT), "开始采集"
        )
        self._enlarge_action_button(self.crawl_button, minimum_width=230)
        self.crawl_button.clicked.connect(self.start_crawl)

        form.addRow(self._label("关键词"), self.keyword)
        form.addRow(self._label("类型"), self.result_type)
        form.addRow(self._label("时间范围"), self.time_range)
        form.addRow(self._label("搜索框超时（秒）"), self.input_timeout)
        form.addRow(self._label("详情页间隔（秒）"), self.detail_delay)
        form.addRow(QLabel(), self.headless)
        card.layout().addWidget(
            form_container, 0, Qt.AlignmentFlag.AlignHCenter
        )
        card.layout().addWidget(
            self.crawl_button, 0, Qt.AlignmentFlag.AlignHCenter
        )
        page_layout.addWidget(card)
        page_layout.addStretch(1)
        return page

    def _build_browser_card(self) -> QFrame:
        card = self._card(
            "浏览器准备",
            "优先使用系统安装的 Chrome / Edge；如未找到则可下载 Chromium。",
        )
        self.browser_badge = AdaptivePushButton("浏览器检测中…")
        self.browser_badge.setMinimumWidth(180)
        self.browser_badge.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.browser_badge.setToolTip("正在检测浏览器。")
        self.browser_badge.clicked.connect(self.handle_browser_click)
        card.layout().addWidget(self.browser_badge, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _build_analyze_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("pageContent")
        page_layout = QVBoxLayout(page)
        page_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(14)
        page_layout.addWidget(self._build_transcript_cookie_card())
        card = self._card("补全视频口播", "")
        form_container = QWidget()
        form_container.setObjectName("analyzeFormContainer")
        form_container.setFixedWidth(600)
        form = QFormLayout(form_container)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.sheets = LineEdit()
        self.sheets.setPlaceholderText("请输入已爬取的关键字")
        self.limit = LineEdit()
        self.limit.setPlaceholderText("留空表示不限")
        self.analyze_timeout = self._spin(1, 600, 90)
        self.analyze_delay = self._spin(0, 60, 0)
        self.overwrite = CheckBox("覆盖已有口播")
        self.analyze_button = AdaptivePrimaryPushButton(
            FIF.VIDEO.icon(Theme.LIGHT), "开始提取口播"
        )
        self._enlarge_action_button(self.analyze_button, minimum_width=230)
        self.analyze_button.clicked.connect(self.start_analyze)

        form.addRow(self._label("Sheet（可选，逗号分隔）"), self.sheets)
        form.addRow(self._label("最多处理条数（可选）"), self.limit)
        form.addRow(self._label("单条超时（秒）"), self.analyze_timeout)
        form.addRow(self._label("请求间隔（秒）"), self.analyze_delay)
        form.addRow(QLabel(), self.overwrite)
        card.layout().addWidget(
            form_container, 0, Qt.AlignmentFlag.AlignHCenter
        )
        card.layout().addWidget(
            self.analyze_button, 0, Qt.AlignmentFlag.AlignHCenter
        )
        page_layout.addWidget(card)
        page_layout.addStretch(1)
        return page

    def _build_crawler_cookie_card(self) -> QFrame:
        card = self._card(
            "爬虫Cookie检测",
            "检测 Crawl4AI 的 Douhot 登录 Profile；失效后点击状态按钮即可扫码登录。",
        )
        self.crawler_cookie_badge = AdaptivePushButton("爬虫 Cookie 检测中…")
        self.crawler_cookie_badge.setMinimumWidth(180)
        self.crawler_cookie_badge.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.crawler_cookie_badge.setToolTip("点击检查爬虫 Cookie。")
        self.crawler_cookie_badge.clicked.connect(self.handle_crawler_cookie_click)
        card.layout().addWidget(
            self.crawler_cookie_badge, 0, Qt.AlignmentFlag.AlignLeft
        )
        return card

    def _build_transcript_cookie_card(self) -> QFrame:
        card = self._card(
            "口播Cookie检测",
            "用于 www.douyin.com 的 cookie.config；过期后请登录网站并手动粘贴新 Cookie。",
        )
        status_layout = QHBoxLayout()
        self.transcript_cookie_badge = AdaptivePushButton("口播 Cookie 检测中…")
        self.transcript_cookie_badge.setMinimumWidth(180)
        self.transcript_cookie_badge.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.transcript_cookie_badge.setToolTip("点击检查口播 Cookie。")
        self.transcript_cookie_badge.clicked.connect(
            self.handle_transcript_cookie_click
        )
        status_layout.addWidget(self.transcript_cookie_badge)
        status_layout.addStretch(1)
        card.layout().addLayout(status_layout)

        self.transcript_cookie_input = TextEdit()
        self.transcript_cookie_input.setPlaceholderText(
            "粘贴从 https://www.douyin.com/ 复制的完整 Cookie；保存后将覆盖 cookie.config。"
        )
        self.transcript_cookie_input.setFixedHeight(92)
        card.layout().addWidget(self.transcript_cookie_input)
        self.save_transcript_cookie_button = AdaptivePrimaryPushButton(
            FIF.SAVE.icon(Theme.LIGHT), "保存口播 Cookie 并检测"
        )
        self._enlarge_action_button(
            self.save_transcript_cookie_button, minimum_width=230
        )
        self.save_transcript_cookie_button.clicked.connect(
            self.save_transcript_cookie_input
        )
        card.layout().addWidget(
            self.save_transcript_cookie_button, 0, Qt.AlignmentFlag.AlignRight
        )
        return card

    def _build_status(self) -> QFrame:
        status = QFrame()
        status.setObjectName("statusStrip")
        layout = QHBoxLayout(status)
        layout.setContentsMargins(15, 10, 12, 10)
        self.status_dot = BodyLabel("●")
        self.status_text = BodyLabel()
        self.stop_button = AdaptivePushButton(FIF.CANCEL, "终止当前任务")
        self._enlarge_action_button(self.stop_button, minimum_width=150)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_task)
        self.login_finish_button = AdaptivePrimaryPushButton(
            FIF.SAVE.icon(Theme.LIGHT), "已完成扫码，保存登录"
        )
        self._enlarge_action_button(
            self.login_finish_button, minimum_width=230
        )
        self.login_finish_button.setEnabled(False)
        self.login_finish_button.clicked.connect(self.finish_login)
        layout.addWidget(self.status_dot)
        layout.addWidget(self.status_text)
        layout.addStretch()
        layout.addWidget(self.login_finish_button)
        layout.addWidget(self.stop_button)
        return status

    @staticmethod
    def _spin(minimum: int, maximum: int, value: int) -> SpinBox:
        spin = SpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    @staticmethod
    def _enlarge_action_button(
        button: AdaptivePushButton | AdaptivePrimaryPushButton,
        *,
        minimum_width: int,
    ) -> None:
        button.setMinimumSize(minimum_width, 40)
        setFont(button, 15)
        button._base_font = QFont(button.font())
        button._fit_text()

    @staticmethod
    def _label(text: str) -> QLabel:
        return CaptionLabel(text)

    def _card(self, title_text: str, hint_text: str) -> QFrame:
        card = CardWidget()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        card.setBorderRadius(12)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(8)
        title = SubtitleLabel(title_text)
        layout.addWidget(title)
        if hint_text:
            hint = CaptionLabel(hint_text)
            hint.setWordWrap(True)
            layout.addWidget(hint)
            layout.addSpacing(10)
        else:
            layout.addSpacing(4)
        return card

    def changeEvent(self, event) -> None:  # type: ignore[override]
        """从任务栏恢复后将窗口重新带到前台。"""

        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and not self.isMinimized()
            and self.isVisible()
        ):
            QTimer.singleShot(0, self._activate_after_restore)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_window_shell_theme)
        if not self._centered_on_startup:
            self._centered_on_startup = True
            QTimer.singleShot(0, self._center_on_screen)
        else:
            QTimer.singleShot(0, self._keep_window_on_screen)

    def _center_on_screen(self) -> None:
        """首次启动时将窗口放在当前屏幕可用工作区中央。"""

        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())
        self._keep_window_on_screen()

    def _activate_after_restore(self) -> None:
        self._keep_window_on_screen()
        self.raise_()
        self.activateWindow()

    def _keep_window_on_screen(self) -> None:
        """将调整尺寸后落在工作区外的窗口移回屏幕。"""

        if self.isMinimized() or self.isMaximized():
            return
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        width = min(self.width(), available.width())
        height = min(self.height(), available.height())
        if (width, height) != (self.width(), self.height()):
            self.resize(width, height)
        frame = self.frameGeometry()
        if not available.intersects(frame):
            frame.moveCenter(available.center())
            self.move(frame.topLeft())

    def start_crawl(self) -> None:
        keyword = self.keyword.text().strip()
        if not keyword:
            self._show_message("缺少关键词", "请输入要爬取的关键词。")
            self.keyword.setFocus()
            return
        if not self._require_browser():
            return
        cookie_status = inspect_douhot_cookie()
        self._show_crawler_cookie_status(cookie_status)
        if cookie_status.state in {"missing", "expired"}:
            self.log.appendPlainText(
                f"\n{cookie_status.label}。请点击“爬虫Cookie检测”的状态按钮开始扫码登录。"
            )
            return
        options = RunOptions(
            keyword=keyword,
            result_type=self.result_type.currentText(),
            time_range=self.time_range.currentText(),
            input_timeout=float(self.input_timeout.value()),
            detail_delay=float(self.detail_delay.value()),
            headless=self.headless.isChecked(),
        )
        self._start_task("热榜爬取", "crawl", options)

    def start_analyze(self) -> None:
        cookie_status = inspect_transcript_cookie()
        self._show_transcript_cookie_status(cookie_status)
        if cookie_status.state in {"missing", "expired"}:
            self.log.appendPlainText(
                f"\n{cookie_status.label}。请在“口播Cookie检测”中粘贴并保存新 Cookie。"
            )
            self.switchTo(self.analyze_interface)
            return
        sheets = []
        for sheet in self.sheets.text().split(","):
            if sheet.strip():
                sheets.append(sheet.strip())
        limit = self.limit.text().strip()
        if limit:
            if not limit.isdigit() or int(limit) < 1:
                self._show_message(
                    "处理条数无效", "最多处理条数必须是大于 0 的整数。"
                )
                self.limit.setFocus()
                return
        options = argparse.Namespace(
            excel=DEFAULT_EXCEL_PATH,
            cookie_file=DEFAULT_COOKIE_PATH,
            sheet=sheets or None,
            callback_url="",
            timeout=float(self.analyze_timeout.value()),
            delay=float(self.analyze_delay.value()),
            limit=int(limit) if limit else None,
            overwrite=self.overwrite.isChecked(),
        )
        self._start_task("口播提取", "analyze", options)

    def _start_login(self) -> None:
        """启动同一 Profile 的扫码登录浏览器。"""

        if not self._require_browser():
            return
        self._start_task("等待扫码登录", "login", None)

    def _start_task(
        self, task_name: str, task_kind: str, payload: object
    ) -> None:
        if self._task_thread and self._task_thread.isRunning():
            self._show_message(
                "任务正在运行", "请先等待当前任务结束，或请求安全停止。"
            )
            return
        thread = QThread(self)
        worker = TaskWorker(task_kind, payload)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.output.connect(self._append_output)
        worker.completed.connect(self._task_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_task_worker)
        self._task_thread = thread
        self._task_worker = worker
        self._task_kind = task_kind
        self.log.appendPlainText(f"\n开始{task_name}…")
        self._set_status(f"运行中 · {task_name}", "#38bdf8")
        self.stop_button.setEnabled(True)
        self.login_finish_button.setEnabled(task_kind == "login")
        self.crawl_button.setEnabled(False)
        self.analyze_button.setEnabled(False)
        self.switchTo(self.log_interface)
        thread.start()

    @Slot(str)
    def _append_output(self, data: str) -> None:
        text = data.rstrip("\n")
        if text:
            self.log.appendPlainText(text)

    @Slot(bool, str)
    def _task_finished(self, succeeded: bool, detail: str) -> None:
        self._set_status(
            "任务完成" if succeeded else f"任务结束：{detail}",
            "#34d399" if succeeded else "#fb7185",
        )
        self._reset_process_controls()
        QTimer.singleShot(250, self._refresh_crawler_cookie_status)
        QTimer.singleShot(250, self._refresh_transcript_cookie_status)

    def _reset_process_controls(self) -> None:
        self.stop_button.setEnabled(False)
        self.login_finish_button.setEnabled(False)
        self.crawl_button.setEnabled(True)
        self.analyze_button.setEnabled(True)
        self._task_kind = None

    def _clear_task_worker(self) -> None:
        self._task_thread = None
        self._task_worker = None

    def finish_login(self) -> None:
        """通知登录子进程关闭 Crawl4AI 浏览器并持久化 Profile。"""

        if not self._task_worker or self._task_kind != "login":
            return
        self._task_worker.request_stop()
        self.login_finish_button.setEnabled(False)
        self._set_status("正在保存登录状态…", "#fbbf24")
        self.log.appendPlainText("\n已确认扫码完成，正在保存 Cookie。")

    def stop_task(self) -> None:
        if not self._task_worker:
            return
        if self._task_kind == "login":
            message = "将关闭登录浏览器并保存当前已有的登录状态。"
        else:
            message = (
                "将完成正在处理的记录，并将本页已采集数据写入 Excel 后退出。\n"
                "尚未取得详情的当前记录会在下次续跑时重新处理。"
            )
        accepted = self._confirm(
            "结束当前任务",
            message,
            confirm_text="结束任务",
        )
        if not accepted:
            return
        self._task_worker.request_stop()
        if self._task_kind == "login":
            self._set_status("正在保存登录状态…", "#fbbf24")
            self.log.appendPlainText("\n正在结束登录并保存 Cookie。")
        else:
            self._set_status("正在安全停止任务…", "#fb7185")
            self.log.appendPlainText("\n已请求安全停止：将写入当前页已完成的数据。")

    def _set_status(self, text: str, color: str) -> None:
        self.status_text.setText(text)
        self.status_dot.setStyleSheet(f"color: {color};")

    def _check_browser(self) -> None:
        self._start_browser_worker(install=False)

    def handle_browser_click(self) -> None:
        if self._browser_thread and self._browser_thread.isRunning():
            return
        if self._browser_ready:
            self._check_browser()
            return
        self._offer_browser_download()

    def _offer_browser_download(self) -> None:
        if self._browser_thread and self._browser_thread.isRunning():
            return
        accepted = self._confirm(
            "下载浏览器",
            "未检测到系统安装的 Chrome / Edge，需要下载 Chromium。\n"
            "下载过程中请保持网络连接，完成后即可扫码登录和开始采集。\n\n"
            "现在下载吗？",
            confirm_text="立即下载",
        )
        if accepted:
            self._start_browser_worker(install=True)

    def _start_browser_worker(self, *, install: bool) -> None:
        if self._browser_thread and self._browser_thread.isRunning():
            return
        self.browser_badge.setText(
            "正在下载浏览器…" if install else "浏览器检测中…"
        )
        self.browser_badge.setToolTip(
            "首次下载可能需要几分钟，请保持网络连接。"
            if install
            else "正在检测浏览器。"
        )
        self.browser_badge.setStyleSheet(
            "color: #38bdf8; background: #13324a; border-radius: 7px; padding: 6px 9px;"
        )
        thread = QThread(self)
        worker = BrowserWorker(install=install)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.output.connect(self._append_output)
        worker.completed.connect(self._show_browser_status)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._browser_check_finished)
        self._browser_thread = thread
        self._browser_worker = worker
        if install:
            self.log.appendPlainText("\n开始下载浏览器…")
            self.switchTo(self.log_interface)
        thread.start()

    @Slot(bool, str)
    def _show_browser_status(self, available: bool, detail: str) -> None:
        self._browser_ready = available
        if available:
            label = "浏览器已就绪"
            self.browser_badge.setText(label)
            self.browser_badge.setToolTip(f"{detail}\n点击可重新检测。")
            self._browser_status_state = "valid"
        else:
            self.browser_badge.setText("下载浏览器")
            self.browser_badge.setToolTip(f"{detail}\n点击开始下载。")
            self._browser_status_state = "expiring"
            if not self._browser_prompted:
                self._browser_prompted = True
                QTimer.singleShot(200, self._offer_browser_download)
        self.browser_badge.setStyleSheet(
            self._cookie_badge_style(self._browser_status_state)
        )

    def _require_browser(self) -> bool:
        if self._browser_ready:
            return True
        self._show_message(
            "浏览器尚未就绪",
            "请先在“浏览器准备”中下载浏览器，完成后再登录或开始采集。",
        )
        return False

    def _refresh_crawler_cookie_status(self) -> None:
        """后台刷新 Profile Cookie 状态，避免与正在运行的浏览器争用界面线程。"""

        if self._cookie_thread and self._cookie_thread.isRunning():
            return
        self.crawler_cookie_badge.setText("爬虫 Cookie 检测中…")
        self.crawler_cookie_badge.setToolTip(
            "正在检查本地 Douhot 浏览器 Profile 的登录 Cookie。"
        )
        self.crawler_cookie_badge.setStyleSheet(
            "color: #38bdf8; background: #13324a; border-radius: 7px; padding: 6px 9px;"
        )

        thread = QThread(self)
        worker = CookieCheckWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.check)
        worker.completed.connect(self._show_crawler_cookie_status)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._cookie_check_finished)
        self._cookie_thread = thread
        self._cookie_worker = worker
        thread.start()

    @staticmethod
    def _cookie_badge_style(status: CookieStatus | str) -> str:
        light_colors = {
            "valid": (
                "#087f5b", "#e8f7f1", "#b7e4d2", "#d8f1e7", "#c8eadc"
            ),
            "expiring": (
                "#8a5a00", "#fff5d6", "#ecd58f", "#ffefbd", "#f8e4a6"
            ),
            "expired": (
                "#b4233c", "#fdecef", "#efbdc6", "#f9dce2", "#f2ccd4"
            ),
            "missing": (
                "#b4233c", "#fdecef", "#efbdc6", "#f9dce2", "#f2ccd4"
            ),
            "unknown": (
                "#52606d", "#edf1f5", "#ccd4dc", "#e2e8ee", "#d7dfe6"
            ),
        }
        dark_colors = {
            "valid": (
                "#72d9b5", "#193a32", "#2d6252", "#20483d", "#285548"
            ),
            "expiring": (
                "#f2c96d", "#3d321b", "#66552b", "#493c20", "#574726"
            ),
            "expired": (
                "#f19aaa", "#40232a", "#70404a", "#4c2931", "#59313a"
            ),
            "missing": (
                "#f19aaa", "#40232a", "#70404a", "#4c2931", "#59313a"
            ),
            "unknown": (
                "#bdc7d1", "#30363d", "#505861", "#394149", "#434b54"
            ),
        }
        colors = dark_colors if isDarkTheme() else light_colors
        state = status.state if isinstance(status, CookieStatus) else status
        foreground, background, border, hover, pressed = colors.get(
            state, colors["unknown"]
        )
        return f"""
            QPushButton {{
                color: {foreground}; background: {background};
                border: 1px solid {border}; border-radius: 7px; padding: 6px 10px;
            }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {pressed}; }}
        """

    def _show_crawler_cookie_status(self, status: CookieStatus) -> None:
        self._crawler_cookie_status = status
        self.crawler_cookie_badge.setText(status.label)
        if status.state in {"missing", "expired"}:
            tooltip = f"{status.detail}\n点击此处打开 Douhot 扫码登录。"
        else:
            tooltip = f"{status.detail}\n点击可重新检测。"
        self.crawler_cookie_badge.setToolTip(tooltip)
        self.crawler_cookie_badge.setStyleSheet(self._cookie_badge_style(status))

    def handle_crawler_cookie_click(self) -> None:
        """点击爬虫 Cookie 状态后检测，必要时启动扫码登录。"""

        cookie_status = inspect_douhot_cookie()
        self._show_crawler_cookie_status(cookie_status)
        if cookie_status.state in {"missing", "expired"}:
            self.log.appendPlainText(
                f"\n{cookie_status.label}，正在打开 Douhot 登录页，请完成扫码。"
            )
            self._start_login()
        elif cookie_status.state == "unknown":
            self._show_message("Cookie 无法检测", cookie_status.detail)
        else:
            self.log.appendPlainText(f"\n{cookie_status.label}：{cookie_status.detail}")

    def _refresh_transcript_cookie_status(self) -> None:
        self._show_transcript_cookie_status(inspect_transcript_cookie())

    def _show_transcript_cookie_status(self, status: CookieStatus) -> None:
        self._transcript_cookie_status = status
        self.transcript_cookie_badge.setText(status.label)
        self.transcript_cookie_badge.setToolTip(f"{status.detail}\n点击可重新检测。")
        self.transcript_cookie_badge.setStyleSheet(
            self._cookie_badge_style(status)
        )

    def handle_transcript_cookie_click(self) -> None:
        status = inspect_transcript_cookie()
        self._show_transcript_cookie_status(status)
        self.log.appendPlainText(f"\n{status.label}：{status.detail}")

    def save_transcript_cookie_input(self) -> None:
        try:
            save_transcript_cookie(self.transcript_cookie_input.toPlainText())
        except ValueError as exc:
            self._show_message("口播 Cookie 无效", str(exc))
            return
        except OSError as exc:
            self._show_message("保存失败", f"无法写入 cookie.config：{exc}")
            return

        self.transcript_cookie_input.clear()
        self._refresh_transcript_cookie_status()
        InfoBar.success(
            title="口播 Cookie 已保存",
            content="已更新 cookie.config 并完成本地检测。",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=5_000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self,
        )

    def download_excel(self) -> None:
        """将当前结果库导出到用户选择的位置。"""

        if self._task_thread and self._task_thread.isRunning():
            self._show_message(
                "任务正在运行", "请在任务结束或安全停止后再下载 Excel。"
            )
            return

        source = RESULT_EXCEL_PATH.resolve()
        if not source.is_file():
            self._show_message(
                "暂无结果文件", f"尚未找到 {RESULT_EXCEL_PATH}，请先完成一次爬取。"
            )
            return

        download_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        )
        filename = f"douhot_result_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        target, _ = QFileDialog.getSaveFileName(
            self,
            "下载 Excel",
            str(Path(download_dir) / filename),
            "Excel 文件 (*.xlsx)",
        )
        if not target:
            return
        target_path = Path(target)
        if target_path.suffix.lower() != ".xlsx":
            target_path = target_path.with_suffix(".xlsx")
        try:
            if target_path.resolve() == source.resolve():
                self._show_message("无需下载", "选择的位置就是当前结果文件。")
                return
            shutil.copy2(source, target_path)
        except OSError as exc:
            self._show_message("下载失败", f"无法导出 Excel：{exc}")
            return

        self.log.appendPlainText(f"\nExcel 已导出：{target_path}")
        InfoBar.success(
            title="下载完成",
            content=f"Excel 已保存到：{target_path}",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            duration=5_000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self,
        )

    def _cookie_check_finished(self) -> None:
        self._cookie_thread = None
        self._cookie_worker = None

    def _browser_check_finished(self) -> None:
        self._browser_thread = None
        self._browser_worker = None

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._task_thread and self._task_thread.isRunning():
            self._show_message(
                "任务仍在运行", "请先使用“终止当前任务”安全停止后再关闭界面。"
            )
            event.ignore()
            return
        if self._browser_thread and self._browser_thread.isRunning():
            self._show_message(
                "浏览器正在下载", "请等待浏览器下载完成后再关闭界面。"
            )
            event.ignore()
            return
        if self._cookie_thread and self._cookie_thread.isRunning():
            self._cookie_thread.quit()
            self._cookie_thread.wait(1_000)
        super().closeEvent(event)


def main() -> None:
    dpi_scale = cfg.get(cfg.dpi_scale)
    if dpi_scale != "Auto":
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(dpi_scale)

    app = QApplication(sys.argv)
    app.setApplicationName("Douhot 数据工作台")
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    app.setFont(QFont("Noto Sans CJK SC", 10))
    fluent_translator = FluentTranslator(
        QLocale(QLocale.Language.Chinese, QLocale.Country.China)
    )
    app.installTranslator(fluent_translator)
    setTheme(cfg.get(cfg.themeMode))
    setThemeColor("#0078d4")
    app.setStyleSheet(APP_STYLESHEET)
    window = DouhotGui()
    window.show()

    interrupted = False
    previous_sigint_handler = signal.getsignal(signal.SIGINT)

    def handle_sigint(_signum, _frame) -> None:
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        if window._task_worker is not None:
            window._task_worker.request_stop()
        window.crawler_cookie_timer.stop()
        window.hide()
        app.quit()

    signal.signal(signal.SIGINT, handle_sigint)
    signal_timer = QTimer()
    signal_timer.setInterval(200)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start()
    try:
        exit_code = app.exec()
    except KeyboardInterrupt:
        handle_sigint(signal.SIGINT, None)
        exit_code = 130
    finally:
        signal_timer.stop()
        signal.signal(signal.SIGINT, previous_sigint_handler)
    raise SystemExit(130 if interrupted else exit_code)


if __name__ == "__main__":
    main()
