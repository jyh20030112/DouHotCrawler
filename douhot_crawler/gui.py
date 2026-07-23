"""Douhot 爬取与口播提取的 Qt 桌面图形界面。"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import os
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (QObject, QStandardPaths, Qt, QThread, QTimer,
                            Signal, Slot)
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (QApplication, QFileDialog, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QSizePolicy, QTabWidget, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, CheckBox,
                            ComboBox)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (InfoBar, InfoBarPosition, LineEdit, PlainTextEdit,
                            PrimaryPushButton, PushButton, SpinBox,
                            SubtitleLabel, TextEdit, Theme, TitleLabel,
                            setTheme)

from douhot_crawler.cookie_status import CookieStatus, inspect_douhot_cookie
from douhot_crawler.analyzer import (DEFAULT_COOKIE_PATH, DEFAULT_EXCEL_PATH,
                                     analyze_excel)
from douhot_crawler.app import run as run_crawler
from douhot_crawler.browser_setup import chromium_status, install_chromium
from douhot_crawler.config import RESULT_EXCEL_PATH
from douhot_crawler.login import run_login
from douhot_crawler.models import RunOptions
from douhot_crawler.transcript_cookie_status import (inspect_transcript_cookie,
                                                     save_transcript_cookie)

# KDE/Wayland 下 Qt 应使用内置的 Wayland text-input 协议，并由 KWin 转交
# 给 Fcitx。系统全局 QT_IM_MODULE=fcitx 会要求 PySide6 加载 ABI 不兼容的
# 系统插件，进而回退为 compose；因此只对本 GUI 进程清除该变量。
# 必须在创建 QApplication 前执行。
os.environ.pop("QT_IM_MODULE", None)


RESULT_TYPES = ("低粉爆款", "视频总榜", "高完播率", "高涨粉率", "高点赞率")
TIME_RANGES = ("近1小时", "近1天", "近3天", "近7天")

APP_STYLESHEET = """
QMainWindow, QWidget#workspace { background: #202020; }
QTabWidget::pane { border: 0; background: transparent; }
QTabBar::tab {
    background: #2b2b2b; color: #b8b8b8; border: 0;
    border-radius: 6px; margin-right: 6px; padding: 9px 18px;
}
QTabBar::tab:selected { background: #3a3a3a; color: white; }
QTabBar::tab:hover { background: #353535; }
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
            while (
                QFontMetrics(font).horizontalAdvance(self.text()) > available_width
                and font.pixelSize() > self.minimum_text_size
            ):
                font.setPixelSize(font.pixelSize() - 1)
        self.setFont(font)


class DouhotGui(QMainWindow):
    """运行爬取任务并呈现实时输出的原生 Qt 界面。"""

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
        self.setWindowTitle("Douhot 爬取与口播提取")
        self.resize(1000, 800)
        self.setMinimumSize(1500, 1200)
        self._build_ui()
        self._set_status("就绪 · 等待开始", "#38bdf8")
        self._check_browser()
        self._refresh_crawler_cookie_status()
        self._refresh_transcript_cookie_status()
        self.crawler_cookie_timer = QTimer(self)
        self.crawler_cookie_timer.setInterval(5 * 60 * 1000)
        self.crawler_cookie_timer.timeout.connect(self._refresh_crawler_cookie_status)
        self.crawler_cookie_timer.start()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("workspace")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)
        outer.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_crawl_tab(), "热榜爬取")
        self.tabs.addTab(self._build_analyze_tab(), "口播提取")
        outer.addWidget(self.tabs)

        outer.addWidget(self._build_status())
        log_label = SubtitleLabel("运行日志")
        outer.addWidget(log_label)
        self.log = PlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1600)
        self.log.setPlaceholderText("任务启动后的实时输出会显示在这里。")
        outer.addWidget(self.log, 1)
        self.setCentralWidget(central)

    def _build_header(self) -> QFrame:
        header = CardWidget()
        header.setBorderRadius(12)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        brand = QLabel("D")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setFixedSize(42, 42)
        brand.setStyleSheet(
            "background: #0078d4; color: white; border-radius: 11px; "
            "font-size: 20px; font-weight: 800;"
        )
        layout.addWidget(brand)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = TitleLabel("Douhot 数据工作台")
        subtitle = CaptionLabel("采集热榜、补全口播，并将结果持续沉淀到 Excel")
        texts.addWidget(title)
        texts.addWidget(subtitle)
        layout.addLayout(texts)
        layout.addStretch()
        self.download_excel_button = AdaptivePushButton(FIF.DOWNLOAD, "下载 Excel")
        self.download_excel_button.setMinimumWidth(120)
        self.download_excel_button.clicked.connect(self.download_excel)
        layout.addWidget(self.download_excel_button)
        return header

    def _build_crawl_tab(self) -> QFrame:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(14)
        page_layout.addWidget(self._build_browser_card())
        page_layout.addWidget(self._build_crawler_cookie_card())
        card = self._card(
            "创建热榜采集任务", "每页数据会即时保存到结果库，适合长时间稳定运行。"
        )
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.keyword = LineEdit()
        self.keyword.setPlaceholderText("例如：美容")
        self.result_type = ComboBox()
        self.result_type.addItems(RESULT_TYPES)
        self.time_range = ComboBox()
        self.time_range.addItems(TIME_RANGES)
        self.time_range.setCurrentText("近7天")
        self.input_timeout = self._spin(1, 300, 30)
        self.detail_delay = self._spin(0, 60, 1)
        self.headless = CheckBox("无头模式")
        self.crawl_button = AdaptivePrimaryPushButton(FIF.SEARCH, "开始爬取")
        self.crawl_button.clicked.connect(self.start_crawl)

        form.addRow(self._label("关键词"), self.keyword)
        form.addRow(self._label("类型"), self.result_type)
        form.addRow(self._label("时间范围"), self.time_range)
        form.addRow(self._label("搜索框超时（秒）"), self.input_timeout)
        form.addRow(self._label("详情页间隔（秒）"), self.detail_delay)
        form.addRow(QLabel(), self.headless)
        form.addRow(QLabel(), self.crawl_button)
        card.layout().addLayout(form)
        page_layout.addWidget(card)
        page_layout.addStretch(1)
        return page

    def _build_browser_card(self) -> QFrame:
        card = self._card(
            "浏览器准备",
            "首次使用需要 Chromium。检测到缺失时可在这里一键下载。",
        )
        self.browser_badge = AdaptivePushButton("Chromium 检测中…")
        self.browser_badge.setMinimumWidth(180)
        self.browser_badge.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.browser_badge.setToolTip("正在检查 Chromium。")
        self.browser_badge.clicked.connect(self.handle_browser_click)
        card.layout().addWidget(self.browser_badge, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _build_analyze_tab(self) -> QFrame:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(14)
        page_layout.addWidget(self._build_transcript_cookie_card())
        card = self._card("补全视频口播", "默认跳过已提取记录，可安全分批处理和续跑。")
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.sheets = LineEdit()
        self.sheets.setPlaceholderText("例如：美容, 大健康")
        self.limit = LineEdit()
        self.limit.setPlaceholderText("留空表示不限")
        self.analyze_timeout = self._spin(1, 600, 90)
        self.analyze_delay = self._spin(0, 60, 0)
        self.overwrite = CheckBox("覆盖已有口播")
        self.analyze_button = AdaptivePrimaryPushButton(FIF.VIDEO, "开始提取口播")
        self.analyze_button.clicked.connect(self.start_analyze)

        form.addRow(self._label("Sheet（可选，逗号分隔）"), self.sheets)
        form.addRow(self._label("最多处理条数（可选）"), self.limit)
        form.addRow(self._label("单条超时（秒）"), self.analyze_timeout)
        form.addRow(self._label("请求间隔（秒）"), self.analyze_delay)
        form.addRow(QLabel(), self.overwrite)
        form.addRow(QLabel(), self.analyze_button)
        card.layout().addLayout(form)
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
            FIF.SAVE, "保存口播 Cookie 并检测"
        )
        self.save_transcript_cookie_button.clicked.connect(
            self.save_transcript_cookie_input
        )
        card.layout().addWidget(
            self.save_transcript_cookie_button, 0, Qt.AlignmentFlag.AlignRight
        )
        return card

    def _build_status(self) -> QFrame:
        status = CardWidget()
        status.setBorderRadius(10)
        layout = QHBoxLayout(status)
        layout.setContentsMargins(15, 10, 12, 10)
        self.status_dot = BodyLabel("●")
        self.status_text = BodyLabel()
        self.stop_button = AdaptivePushButton(FIF.CANCEL, "终止当前任务")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_task)
        self.login_finish_button = AdaptivePrimaryPushButton(
            FIF.SAVE, "已完成扫码，保存登录"
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
    def _label(text: str) -> QLabel:
        return CaptionLabel(text)

    def _card(self, title_text: str, hint_text: str) -> QFrame:
        card = CardWidget()
        card.setBorderRadius(12)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(8)
        title = SubtitleLabel(title_text)
        hint = CaptionLabel(hint_text)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(10)
        return card

    def start_crawl(self) -> None:
        keyword = self.keyword.text().strip()
        if not keyword:
            QMessageBox.warning(self, "缺少关键词", "请输入要爬取的关键词。")
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
            self.tabs.setCurrentIndex(1)
            return
        sheets = []
        for sheet in self.sheets.text().split(","):
            if sheet.strip():
                sheets.append(sheet.strip())
        limit = self.limit.text().strip()
        if limit:
            if not limit.isdigit() or int(limit) < 1:
                QMessageBox.warning(
                    self, "处理条数无效", "最多处理条数必须是大于 0 的整数。"
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
            QMessageBox.information(
                self, "任务正在运行", "请先等待当前任务结束，或请求安全停止。"
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
        accepted = QMessageBox.question(
            self,
            "结束当前任务",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if accepted != QMessageBox.StandardButton.Yes:
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
        accepted = QMessageBox.question(
            self,
            "下载 Chromium",
            "首次使用爬取功能需要下载 Chromium。\n"
            "下载过程中请保持网络连接，完成后即可扫码登录和开始爬取。\n\n"
            "现在下载吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if accepted == QMessageBox.StandardButton.Yes:
            self._start_browser_worker(install=True)

    def _start_browser_worker(self, *, install: bool) -> None:
        if self._browser_thread and self._browser_thread.isRunning():
            return
        self.browser_badge.setText(
            "正在下载 Chromium…" if install else "Chromium 检测中…"
        )
        self.browser_badge.setToolTip(
            "首次下载可能需要几分钟，请保持网络连接。"
            if install
            else "正在检查 Chromium。"
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
            self.log.appendPlainText("\n开始下载 Chromium…")
        thread.start()

    @Slot(bool, str)
    def _show_browser_status(self, available: bool, detail: str) -> None:
        self._browser_ready = available
        if available:
            self.browser_badge.setText("Chromium 已就绪")
            self.browser_badge.setToolTip(f"{detail}\n点击可重新检测。")
            foreground, background = "#34d399", "#123a35"
        else:
            self.browser_badge.setText("下载 Chromium")
            self.browser_badge.setToolTip(f"{detail}\n点击开始下载。")
            foreground, background = "#fbbf24", "#3d3112"
            if not self._browser_prompted:
                self._browser_prompted = True
                QTimer.singleShot(200, self._offer_browser_download)
        self.browser_badge.setStyleSheet(
            "border-radius: 7px; padding: 6px 9px; "
            f"color: {foreground}; background: {background};"
        )

    def _require_browser(self) -> bool:
        if self._browser_ready:
            return True
        QMessageBox.information(
            self,
            "Chromium 尚未就绪",
            "请先在“浏览器准备”中下载 Chromium，完成后再登录或开始爬取。",
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
    def _cookie_colors(status: CookieStatus) -> tuple[str, str]:
        colors = {
            "valid": ("#34d399", "#123a35"),
            "expiring": ("#fbbf24", "#3d3112"),
            "expired": ("#fb7185", "#3a1b2a"),
            "missing": ("#fb7185", "#3a1b2a"),
            "unknown": ("#94a3b8", "#2b3b55"),
        }
        return colors.get(status.state, colors["unknown"])

    def _show_crawler_cookie_status(self, status: CookieStatus) -> None:
        foreground, background = self._cookie_colors(status)
        self.crawler_cookie_badge.setText(status.label)
        if status.state in {"missing", "expired"}:
            tooltip = f"{status.detail}\n点击此处打开 Douhot 扫码登录。"
        else:
            tooltip = f"{status.detail}\n点击可重新检测。"
        self.crawler_cookie_badge.setToolTip(tooltip)
        self.crawler_cookie_badge.setStyleSheet(
            "border-radius: 7px; padding: 6px 9px; "
            f"color: {foreground}; background: {background};"
        )

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
            QMessageBox.warning(self, "Cookie 无法检测", cookie_status.detail)
        else:
            self.log.appendPlainText(f"\n{cookie_status.label}：{cookie_status.detail}")

    def _refresh_transcript_cookie_status(self) -> None:
        self._show_transcript_cookie_status(inspect_transcript_cookie())

    def _show_transcript_cookie_status(self, status: CookieStatus) -> None:
        foreground, background = self._cookie_colors(status)
        self.transcript_cookie_badge.setText(status.label)
        self.transcript_cookie_badge.setToolTip(f"{status.detail}\n点击可重新检测。")
        self.transcript_cookie_badge.setStyleSheet(
            "border-radius: 7px; padding: 6px 9px; "
            f"color: {foreground}; background: {background};"
        )

    def handle_transcript_cookie_click(self) -> None:
        status = inspect_transcript_cookie()
        self._show_transcript_cookie_status(status)
        self.log.appendPlainText(f"\n{status.label}：{status.detail}")

    def save_transcript_cookie_input(self) -> None:
        try:
            save_transcript_cookie(self.transcript_cookie_input.toPlainText())
        except ValueError as exc:
            QMessageBox.warning(self, "口播 Cookie 无效", str(exc))
            return
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", f"无法写入 cookie.config：{exc}")
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
            QMessageBox.information(
                self, "任务正在运行", "请在任务结束或安全停止后再下载 Excel。"
            )
            return

        source = RESULT_EXCEL_PATH.resolve()
        if not source.is_file():
            QMessageBox.information(
                self, "暂无结果文件", "尚未找到 result/result.xlsx，请先完成一次爬取。"
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
                QMessageBox.information(
                    self, "无需下载", "选择的位置就是当前结果文件。"
                )
                return
            shutil.copy2(source, target_path)
        except OSError as exc:
            QMessageBox.critical(self, "下载失败", f"无法导出 Excel：{exc}")
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
            QMessageBox.information(
                self, "任务仍在运行", "请先使用“终止当前任务”安全停止后再关闭界面。"
            )
            event.ignore()
            return
        if self._browser_thread and self._browser_thread.isRunning():
            QMessageBox.information(
                self, "浏览器正在下载", "请等待 Chromium 下载完成后再关闭界面。"
            )
            event.ignore()
            return
        if self._cookie_thread and self._cookie_thread.isRunning():
            self._cookie_thread.quit()
            self._cookie_thread.wait(1_000)
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Douhot 数据工作台")
    app.setFont(QFont("Noto Sans CJK SC", 10))
    setTheme(Theme.DARK)
    app.setStyleSheet(APP_STYLESHEET)
    window = DouhotGui()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
