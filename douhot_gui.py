"""Douhot 爬取与口播提取的桌面图形界面。"""

import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

PROJECT_ROOT = Path(__file__).resolve().parent
RESULT_TYPES = ("低粉爆款", "视频总榜", "高完播率", "高涨粉率", "高点赞率")
TIME_RANGES = ("近1小时", "近1天", "近3天", "近7天")
COLORS = {
    "canvas": "#0B1220",
    "surface": "#111C2E",
    "card": "#16243A",
    "border": "#2B3B55",
    "text": "#F1F5F9",
    "muted": "#94A3B8",
    "primary": "#38BDF8",
    "primary_active": "#0EA5E9",
    "success": "#34D399",
    "danger": "#FB7185",
    "log": "#08111F",
}


class DouhotGui:
    """运行已有命令行脚本的轻量桌面界面。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Douhot 爬取与口播提取")
        self.root.geometry("980x760")
        self.root.minsize(800, 620)
        self.root.configure(background=COLORS["canvas"])
        self.ui_font = self._configure_fonts()
        self._configure_theme()

        self.process: subprocess.Popen[str] | None = None
        self.events: queue.Queue[tuple[str, str | int]] = queue.Queue()
        self.status = tk.StringVar(value="就绪 · 等待开始")
        self._build_ui()
        self._set_status("就绪 · 等待开始", COLORS["primary"])
        self.root.after(100, self._drain_events)

    def _configure_fonts(self) -> str:
        """优先使用可显示中文的系统字体。"""

        available_fonts = set(tkfont.families(self.root))
        # Maple Mono NF CN 的 fontconfig 声明含中文字符，但在部分 Tk/X11
        # 环境中会把这些字符渲染为不可见字形。界面统一使用 Noto 的 CJK
        # 字体，而不是依赖系统的字体回退链。
        candidates = (
            "Noto Sans CJK SC",
            "Noto Sans Mono CJK SC",
            "Microsoft YaHei",
            "PingFang SC",
            "SimHei",
        )
        family = next(
            (candidate for candidate in candidates if candidate in available_fonts),
            tkfont.nametofont("TkDefaultFont").cget("family"),
        )

        for font_name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkTooltipFont",
            "TkFixedFont",
        ):
            try:
                tkfont.nametofont(font_name).configure(family=family)
            except tk.TclError:
                continue

        # 用实际 Font 对象绑定到 Tk/ttk，而不是只传字体族字符串；这样页签、
        # Combobox 弹出菜单和按钮也会使用同一个可显示中文的字体。
        self.base_font = tkfont.Font(self.root, family=family, size=10)
        self.heading_font = tkfont.Font(
            self.root, family=family, size=13, weight="bold"
        )
        self.title_font = tkfont.Font(self.root, family=family, size=20, weight="bold")
        self.button_font = tkfont.Font(self.root, family=family, size=10, weight="bold")
        self.root.option_add("*Font", self.base_font)
        self.root.option_add("*TCombobox*Listbox.font", self.base_font)
        return family

    def _configure_theme(self) -> None:
        """配置深色桌面视觉系统。"""

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            ".",
            background=COLORS["canvas"],
            foreground=COLORS["text"],
            font=self.base_font,
        )
        style.configure("TFrame", background=COLORS["canvas"])
        style.configure("Card.TFrame", background=COLORS["card"])
        style.configure(
            "TLabel",
            background=COLORS["canvas"],
            foreground=COLORS["text"],
            font=self.base_font,
        )
        style.configure(
            "HeaderTitle.TLabel",
            background=COLORS["card"],
            foreground=COLORS["text"],
            font=self.title_font,
        )
        style.configure(
            "HeaderSub.TLabel",
            background=COLORS["card"],
            foreground=COLORS["muted"],
            font=self.base_font,
        )
        style.configure(
            "CardTitle.TLabel",
            background=COLORS["card"],
            foreground=COLORS["text"],
            font=self.heading_font,
        )
        style.configure(
            "CardHint.TLabel",
            background=COLORS["card"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "Form.TLabel", background=COLORS["card"], foreground=COLORS["muted"]
        )
        style.configure(
            "TEntry",
            fieldbackground="#0D182A",
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=(10, 7),
            font=self.base_font,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#0D182A",
            foreground=COLORS["text"],
            background=COLORS["card"],
            bordercolor=COLORS["border"],
            padding=(8, 5),
            font=self.base_font,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#0D182A")],
            foreground=[("readonly", COLORS["text"])],
            selectbackground=[("readonly", "#0D182A")],
            selectforeground=[("readonly", COLORS["text"])],
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["primary"],
            foreground="#062136",
            borderwidth=0,
            padding=(16, 9),
            font=self.button_font,
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", COLORS["primary_active"]),
                ("disabled", COLORS["border"]),
            ],
            foreground=[("disabled", COLORS["muted"])],
        )
        style.configure(
            "Danger.TButton",
            background="#3A1B2A",
            foreground="#FDA4AF",
            borderwidth=0,
            padding=(12, 8),
        )
        style.map("Danger.TButton", background=[("active", "#542033")])
        style.configure(
            "TCheckbutton",
            background=COLORS["card"],
            foreground=COLORS["text"],
            font=self.base_font,
        )
        style.map("TCheckbutton", background=[("active", COLORS["card"])])
        style.configure("TNotebook", background=COLORS["canvas"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            padding=(20, 10),
            font=self.button_font,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["card"]), ("active", COLORS["surface"])],
            foreground=[("selected", COLORS["primary"]), ("active", COLORS["text"])],
        )

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=18)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="Card.TFrame", padding=(22, 18))
        header.pack(fill="x", pady=(0, 16))
        brand = tk.Label(
            header,
            text="D",
            background=COLORS["primary"],
            foreground="#062136",
            font=self.title_font,
            width=2,
            pady=4,
        )
        brand.pack(side="left", padx=(0, 14))
        title_group = ttk.Frame(header, style="Card.TFrame")
        title_group.pack(side="left", fill="x", expand=True)
        ttk.Label(
            title_group, text="Douhot 数据工作台", style="HeaderTitle.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            title_group,
            text="采集热榜、补全口播，并将结果持续沉淀到 Excel",
            style="HeaderSub.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(
            header,
            text="测试版",
            background="#13324A",
            foreground=COLORS["primary"],
            font=self.button_font,
            padx=10,
            pady=5,
        ).pack(side="right")

        notebook = ttk.Notebook(container)
        notebook.pack(fill="x", pady=(0, 14))
        crawl_tab = ttk.Frame(notebook, padding=4)
        analyze_tab = ttk.Frame(notebook, padding=4)
        notebook.add(crawl_tab, text="热榜爬取")
        notebook.add(analyze_tab, text="口播提取")

        self._build_crawl_tab(crawl_tab)
        self._build_analyze_tab(analyze_tab)

        status_frame = ttk.Frame(container, style="Card.TFrame", padding=(16, 12))
        status_frame.pack(fill="x", pady=(0, 14))
        self.status_dot = tk.Label(
            status_frame,
            text="●",
            background=COLORS["card"],
            foreground=COLORS["primary"],
        )
        self.status_dot.pack(side="left", padx=(0, 8))
        ttk.Label(status_frame, textvariable=self.status, style="CardHint.TLabel").pack(
            side="left"
        )
        self.stop_button = ttk.Button(
            status_frame,
            text="终止当前任务",
            command=self.stop_task,
            state="disabled",
            style="Danger.TButton",
        )
        self.stop_button.pack(side="right")

        log_label = ttk.Frame(container)
        log_label.pack(fill="x", pady=(0, 7))
        ttk.Label(log_label, text="运行日志", font=self.heading_font).pack(side="left")
        ttk.Label(
            log_label, text="实时显示子进程输出", foreground=COLORS["muted"]
        ).pack(side="left", padx=(10, 0))
        log_frame = tk.Frame(container, background=COLORS["border"], padx=1, pady=1)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(
            log_frame,
            wrap="word",
            state="disabled",
            font=self.base_font,
            background=COLORS["log"],
            foreground="#C7D2FE",
            insertbackground=COLORS["text"],
            relief="flat",
            padx=14,
            pady=12,
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _build_crawl_tab(self, parent: ttk.Frame) -> None:
        self.keyword_var = tk.StringVar()
        self.result_type_var = tk.StringVar(value="低粉爆款")
        self.time_range_var = tk.StringVar(value="近7天")
        self.input_timeout_var = tk.StringVar(value="30")
        self.detail_delay_var = tk.StringVar(value="1")
        self.headless_var = tk.BooleanVar(value=False)

        card = ttk.Frame(parent, style="Card.TFrame", padding=22)
        card.pack(fill="x")
        ttk.Label(card, text="创建热榜采集任务", style="CardTitle.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            card,
            text="每页数据会即时保存到结果库，适合长时间稳定运行。",
            style="CardHint.TLabel",
        ).pack(anchor="w", pady=(4, 16))
        form = ttk.Frame(card, style="Card.TFrame")
        form.pack(fill="x")
        parent = form

        self._field(
            parent, 0, "关键词", ttk.Entry(parent, textvariable=self.keyword_var)
        )
        self._field(
            parent,
            1,
            "类型",
            ttk.Combobox(
                parent,
                textvariable=self.result_type_var,
                values=RESULT_TYPES,
                state="readonly",
            ),
        )
        self._field(
            parent,
            2,
            "时间范围",
            ttk.Combobox(
                parent,
                textvariable=self.time_range_var,
                values=TIME_RANGES,
                state="readonly",
            ),
        )
        self._field(
            parent,
            3,
            "搜索框超时（秒）",
            ttk.Entry(parent, textvariable=self.input_timeout_var),
        )
        self._field(
            parent,
            4,
            "详情页间隔（秒）",
            ttk.Entry(parent, textvariable=self.detail_delay_var),
        )
        ttk.Checkbutton(parent, text="无头模式", variable=self.headless_var).grid(
            row=5,
            column=1,
            sticky="w",
            pady=6,
        )
        ttk.Button(
            parent,
            text="开始爬取",
            command=self.start_crawl,
            style="Accent.TButton",
        ).grid(
            row=6,
            column=1,
            sticky="w",
            pady=(12, 0),
        )

    def _build_analyze_tab(self, parent: ttk.Frame) -> None:
        self.sheets_var = tk.StringVar()
        self.limit_var = tk.StringVar()
        self.analyze_timeout_var = tk.StringVar(value="90")
        self.analyze_delay_var = tk.StringVar(value="0")
        self.overwrite_var = tk.BooleanVar(value=False)

        card = ttk.Frame(parent, style="Card.TFrame", padding=22)
        card.pack(fill="x")
        ttk.Label(card, text="补全视频口播", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            text="默认跳过已提取记录，可安全分批处理和续跑。",
            style="CardHint.TLabel",
        ).pack(anchor="w", pady=(4, 16))
        form = ttk.Frame(card, style="Card.TFrame")
        form.pack(fill="x")
        parent = form

        self._field(
            parent,
            0,
            "Sheet（可选，逗号分隔）",
            ttk.Entry(parent, textvariable=self.sheets_var),
        )
        self._field(
            parent,
            1,
            "最多处理条数（可选）",
            ttk.Entry(parent, textvariable=self.limit_var),
        )
        self._field(
            parent,
            2,
            "单条超时（秒）",
            ttk.Entry(parent, textvariable=self.analyze_timeout_var),
        )
        self._field(
            parent,
            3,
            "请求间隔（秒）",
            ttk.Entry(parent, textvariable=self.analyze_delay_var),
        )
        ttk.Checkbutton(parent, text="覆盖已有口播", variable=self.overwrite_var).grid(
            row=4,
            column=1,
            sticky="w",
            pady=6,
        )
        ttk.Button(
            parent,
            text="开始提取口播",
            command=self.start_analyze,
            style="Accent.TButton",
        ).grid(
            row=5,
            column=1,
            sticky="w",
            pady=(12, 0),
        )

    @staticmethod
    def _field(parent: ttk.Frame, row: int, label: str, widget: ttk.Widget) -> None:
        ttk.Label(parent, text=label, width=20, style="Form.TLabel").grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=6,
        )
        widget.grid(row=row, column=1, sticky="ew", pady=6)
        parent.columnconfigure(1, weight=1)

    def start_crawl(self) -> None:
        keyword = self.keyword_var.get().strip()
        if not keyword:
            messagebox.showerror("缺少关键词", "请输入要爬取的关键词。")
            return

        command = [
            sys.executable,
            "-u",
            "crawler.py",
            keyword,
            "--result-type",
            self.result_type_var.get(),
            "--time-range",
            self.time_range_var.get(),
            "--input-timeout",
            self.input_timeout_var.get().strip(),
            "--detail-delay",
            self.detail_delay_var.get().strip(),
        ]
        if self.headless_var.get():
            command.append("--headless")
        self._start(command, "热榜爬取")

    def start_analyze(self) -> None:
        command = [
            sys.executable,
            "-u",
            "douhot_analyze.py",
            "--timeout",
            self.analyze_timeout_var.get().strip(),
            "--delay",
            self.analyze_delay_var.get().strip(),
        ]
        for sheet_name in self.sheets_var.get().split(","):
            if sheet_name.strip():
                command.extend(("--sheet", sheet_name.strip()))
        if self.limit_var.get().strip():
            command.extend(("--limit", self.limit_var.get().strip()))
        if self.overwrite_var.get():
            command.append("--overwrite")
        self._start(command, "口播提取")

    def _start(self, command: list[str], task_name: str) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showwarning("任务进行中", "请先等待当前任务完成或终止。")
            return

        self._append_log(f"\n$ {' '.join(command)}\n")
        self._set_status(f"{task_name}运行中", COLORS["primary"])
        self.stop_button.configure(state="normal")
        self.process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        threading.Thread(target=self._read_output, daemon=True).start()

    def _read_output(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            self.events.put(("output", line))
        self.events.put(("finished", self.process.wait()))

    def _drain_events(self) -> None:
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "output":
                    self._append_log(str(value))
                else:
                    exit_code = int(value)
                    self._set_status(
                        "任务完成" if exit_code == 0 else f"任务结束（{exit_code}）",
                        COLORS["success"] if exit_code == 0 else COLORS["danger"],
                    )
                    self.stop_button.configure(state="disabled")
                    self.process = None
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status.set(text)
        self.status_dot.configure(foreground=color)

    def stop_task(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        if not messagebox.askyesno(
            "安全停止任务",
            "将完成正在处理的记录，并将本页已采集数据写入 Excel 后退出。"
            "尚未取得详情的当前记录会在下次续跑时重新处理。",
        ):
            return
        self.process.terminate()
        self._set_status("正在安全停止任务…", COLORS["danger"])
        self._append_log("\n已请求安全停止：将写入当前页已完成的数据。\n")


def main() -> None:
    root = tk.Tk()
    # uv 随附的 Tk 9 默认编译为 no-xft（无 fontconfig 支持），
    # 导致中文字符宽度为 0 并显示为空白。本项目通过 LD_PRELOAD 注入
    # 本地编译的 --enable-xft 版本 Tk 解决，请使用 douhot_gui.sh 启动。
    probe = tkfont.Font(root, family="Noto Sans CJK SC", size=10)
    if probe.measure("热榜爬取") == 0:
        root.destroy()
        print(
            "⚠️  当前 Tk 不支持中文字体（缺少 Xft/fontconfig 后端）。\n"
            "   请改用启动脚本:  ./douhot_gui.sh\n"
            "   或先编译安装带 Xft 支持的 Tcl/Tk 9.0 到 ~/.local 。",
            file=sys.stderr,
        )
        from douhot_web_gui import main as run_web_gui

        run_web_gui()
        return
    DouhotGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
