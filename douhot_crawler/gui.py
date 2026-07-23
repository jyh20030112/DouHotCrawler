"""Douhot 爬取与口播提取的 Qt 桌面图形界面。"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (QObject, QProcess, QStandardPaths, Qt, QThread,
                            QTimer, Signal, Slot)
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
from douhot_crawler.transcript_cookie_status import (inspect_transcript_cookie,
                                                     save_transcript_cookie)

# KDE/Wayland 下 Qt 应使用内置的 Wayland text-input 协议，并由 KWin 转交
# 给 Fcitx。系统全局 QT_IM_MODULE=fcitx 会要求 PySide6 加载 ABI 不兼容的
# 系统插件，进而回退为 compose；因此只对本 GUI 进程清除该变量。
# 必须在创建 QApplication 前执行。
os.environ.pop("QT_IM_MODULE", None)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
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
    """启动既有 CLI 并呈现实时输出的原生 Qt 界面。"""

    def __init__(self) -> None:
        super().__init__()
        self.process: QProcess | None = None
        self._task_kind: str | None = None
        self._cookie_thread: QThread | None = None
        self._cookie_worker: CookieCheckWorker | None = None
        self.setWindowTitle("Douhot 爬取与口播提取")
        self.resize(1000, 800)
        self.setMinimumSize(1500, 1200)
        self._build_ui()
        self._set_status("就绪 · 等待开始", "#38bdf8")
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
        cookie_status = inspect_douhot_cookie()
        self._show_crawler_cookie_status(cookie_status)
        if cookie_status.state in {"missing", "expired"}:
            self.log.appendPlainText(
                f"\n{cookie_status.label}。请点击“爬虫Cookie检测”的状态按钮开始扫码登录。"
            )
            return
        arguments = [
            "-u",
            "-m",
            "douhot_crawler",
            keyword,
            "--result-type",
            self.result_type.currentText(),
            "--time-range",
            self.time_range.currentText(),
            "--input-timeout",
            str(self.input_timeout.value()),
            "--detail-delay",
            str(self.detail_delay.value()),
        ]
        if self.headless.isChecked():
            arguments.append("--headless")
        self._start_process("热榜爬取", arguments, "crawl")

    def start_analyze(self) -> None:
        cookie_status = inspect_transcript_cookie()
        self._show_transcript_cookie_status(cookie_status)
        if cookie_status.state in {"missing", "expired"}:
            self.log.appendPlainText(
                f"\n{cookie_status.label}。请在“口播Cookie检测”中粘贴并保存新 Cookie。"
            )
            self.tabs.setCurrentIndex(1)
            return
        arguments = [
            "-u",
            "-m",
            "douhot_crawler.analyzer",
            "--timeout",
            str(self.analyze_timeout.value()),
            "--delay",
            str(self.analyze_delay.value()),
        ]
        for sheet in self.sheets.text().split(","):
            if sheet.strip():
                arguments.extend(("--sheet", sheet.strip()))
        limit = self.limit.text().strip()
        if limit:
            if not limit.isdigit() or int(limit) < 1:
                QMessageBox.warning(
                    self, "处理条数无效", "最多处理条数必须是大于 0 的整数。"
                )
                self.limit.setFocus()
                return
            arguments.extend(("--limit", limit))
        if self.overwrite.isChecked():
            arguments.append("--overwrite")
        self._start_process("口播提取", arguments, "analyze")

    def _start_login(self) -> None:
        """启动同一 Profile 的扫码登录浏览器。"""

        self._start_process(
            "等待扫码登录", ["-u", "-m", "douhot_crawler.login_cli"], "login"
        )

    def _start_process(
        self, task_name: str, arguments: list[str], task_kind: str
    ) -> None:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(
                self, "任务正在运行", "请先等待当前任务结束，或请求安全停止。"
            )
            return
        process = QProcess(self)
        process.setWorkingDirectory(str(PROJECT_ROOT))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.finished.connect(self._process_finished)
        process.errorOccurred.connect(self._process_error)
        self.process = process
        self._task_kind = task_kind
        self.log.appendPlainText("\n$ " + shlex.join([sys.executable, *arguments]))
        self._set_status(f"运行中 · {task_name}", "#38bdf8")
        self.stop_button.setEnabled(True)
        self.login_finish_button.setEnabled(task_kind == "login")
        self.crawl_button.setEnabled(False)
        self.analyze_button.setEnabled(False)
        process.start(sys.executable, arguments)

    def _read_stdout(self) -> None:
        if self.process:
            self._append_output(bytes(self.process.readAllStandardOutput()))

    def _read_stderr(self) -> None:
        if self.process:
            self._append_output(bytes(self.process.readAllStandardError()))

    def _append_output(self, data: bytes) -> None:
        text = data.decode("utf-8", errors="replace").rstrip("\n")
        if text:
            self.log.appendPlainText(text)

    def _process_finished(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        succeeded = exit_code == 0 and status == QProcess.ExitStatus.NormalExit
        self._set_status(
            "任务完成" if succeeded else f"任务结束（{exit_code}）",
            "#34d399" if succeeded else "#fb7185",
        )
        self._reset_process_controls()
        QTimer.singleShot(250, self._refresh_crawler_cookie_status)
        QTimer.singleShot(250, self._refresh_transcript_cookie_status)

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.log.appendPlainText("\n无法启动 Python 子进程。")
            self._set_status("无法启动任务", "#fb7185")
            self._reset_process_controls()

    def _reset_process_controls(self) -> None:
        self.stop_button.setEnabled(False)
        self.login_finish_button.setEnabled(False)
        self.crawl_button.setEnabled(True)
        self.analyze_button.setEnabled(True)
        self.process = None
        self._task_kind = None

    def finish_login(self) -> None:
        """通知登录子进程关闭 Crawl4AI 浏览器并持久化 Profile。"""

        if not self.process or self._task_kind != "login":
            return
        self.process.write(b"q\n")
        self.login_finish_button.setEnabled(False)
        self._set_status("正在保存登录状态…", "#fbbf24")
        self.log.appendPlainText("\n已确认扫码完成，正在保存 Cookie。")

    def stop_task(self) -> None:
        if not self.process or self.process.state() == QProcess.ProcessState.NotRunning:
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
        self.process.terminate()
        if self._task_kind == "login":
            self._set_status("正在保存登录状态…", "#fbbf24")
            self.log.appendPlainText("\n正在结束登录并保存 Cookie。")
        else:
            self._set_status("正在安全停止任务…", "#fb7185")
            self.log.appendPlainText("\n已请求安全停止：将写入当前页已完成的数据。")

    def _set_status(self, text: str, color: str) -> None:
        self.status_text.setText(text)
        self.status_dot.setStyleSheet(f"color: {color};")

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

        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(
                self, "任务正在运行", "请在任务结束或安全停止后再下载 Excel。"
            )
            return

        source = PROJECT_ROOT / "result" / "result.xlsx"
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

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(
                self, "任务仍在运行", "请先使用“终止当前任务”安全停止后再关闭界面。"
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
