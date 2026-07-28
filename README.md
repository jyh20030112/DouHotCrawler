# DouHotCrawler

Douhot 数据工作台 — 按关键词采集 Douhot（抖音热榜）视频数据，提取视频口播文本，结果归档为 Excel。

桌面版无需安装 Python 或任何开发工具，开箱即用。

## 下载

在 [GitHub Releases](https://github.com/jyh20030112/DouHotCrawler/releases) 页面下载最新版本，选择与你的电脑匹配的构建产物：

| 下载文件 | 适用设备 |
|---|---|
| `DouHotCrawler-windows-x86_64.zip` | Windows 电脑（Intel / AMD 处理器） |
| `DouHotCrawler-macos-arm64.zip` | Apple 芯片 Mac（M1 / M2 / M3 / M4 等） |
| `DouHotCrawler-Linux-x86_64.zip` | Linux 电脑（Intel / AMD 处理器） |

> 不确定 Mac 芯片类型：屏幕左上角 Apple 菜单 →「关于本机」，显示"芯片 Apple …"选 `macos-arm64`；显示"处理器 Intel …"选 `macos-x86_64`（Intel Mac 版本暂未提供构建，可自行从源码打包）。

## 首次使用

1. **解压**下载的 zip 文件，保留整个文件夹结构。
2. **启动程序**：
   - **Windows**：双击 `DouHotCrawler.exe`。
   - **macOS**：双击 `DouHotCrawler.app`。若提示"无法验证开发者"，在 Finder 中按住 Control 点击 →「打开」即可。
   - **Linux**：终端执行 `chmod +x DouHotCrawler && ./DouHotCrawler`。
3. **下载浏览器**：首次启动若未检测到系统安装的 Chrome / Edge，程序会提示下载 Chromium。点击"立即下载"，等待完成。
4. **扫码登录**：在"热榜采集"页点击爬虫 Cookie 状态按钮，浏览器打开 Douhot 登录页。扫码完成后回到程序，点击「已完成扫码，保存登录」。
5. **（可选）配置口播 Cookie**：如需提取视频口播，在"口播提取"页粘贴抖音 `www.douyin.com` 的完整 Cookie，点击保存。

后续启动无需重复下载或登录；Cookie 过期后按相同步骤更新即可。

## 功能

### 热榜采集

- 输入关键词（如"美容""大健康"），选择榜单类型（低粉爆款 / 视频总榜 / 高完播率等）和时间范围（近 1 小时 ~ 近 7 天）。
- 自动跳过已采集的视频，支持持续增量补充。
- 每页数据实时写入 Excel，可安全中断不丢数据。

### 口播提取

- 对结果 Excel 中的视频调用提取接口，补全口播文本。
- 支持指定 Sheet、限制处理条数、设置请求间隔。
- 已有口播的记录默认跳过，可勾选覆盖。

### 导出与安全停止

- 任务完成后在"运行日志"页点击「导出 Excel」保存到本地。
- 点击「终止当前任务」会完成当前记录并写入已采集数据后安全退出。

## 命令行工具

开发者和高级用户也可以通过 CLI 使用：

```bash
# 热榜采集
uv run douhot-crawl "关键词" --result-type "低粉爆款" --time-range "近7天"

# 口播提取
uv run douhot-analyze --excel result/result.xlsx --cookie-file cookie.config

# 扫码登录
uv run douhot-login

# 启动图形界面
uv run douhot-gui
```

详细参数见 `--help`。

## 开发

### 环境要求

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) 包管理器

### 本地运行

```bash
git clone https://github.com/jyh20030112/DouHotCrawler.git
cd DouHotCrawler
uv sync
uv run douhot-gui
```

### 运行测试

```bash
uv run python -m unittest discover -s tests -v
```

### 打包

```bash
uv sync --group build
bash scripts/build_package.sh
```

产物在 `dist/DouHotCrawler/`（macOS 为 `dist/DouHotCrawler.app`）。

## 技术栈

| 层 | 技术 |
|---|---|
| GUI | PySide6 + [PySide6-Fluent-Widgets](https://github.com/zhiyiYo/PySide6-Fluent-Widgets) |
| 爬虫 | [Crawl4AI](https://github.com/unclecode/crawl4ai) + Playwright |
| 数据处理 | openpyxl |
| 打包 | PyInstaller（onedir 模式） |
| 包管理 | uv + Hatchling |

## CI / CD

提交到 `main` 分支自动运行测试。推送 `v*` 标签触发：

1. **Tests** — 单元测试（ubuntu）
2. **Package** — 三平台并行构建（Windows / Linux / macOS arm64）
3. **Release** — 自动创建 GitHub Release，上传所有平台的 zip 产物

## 常见问题

### 无法下载 Chromium

检查网络和磁盘空间。Linux 需具备图形桌面环境。

### 无法开始采集

确认"浏览器准备"显示已就绪，且爬虫 Cookie 状态为有效。Cookie 过期或未登录时点击状态按钮重新扫码。

### 口播提取失败

重新从 `www.douyin.com` 复制完整 Cookie 粘贴保存。Cookie 可能因退出登录或过期而失效。

### macOS / Windows 提示未知开发者

未签名应用的正常安全提示。确认从 GitHub Releases 下载，按系统提示继续打开即可。

## 隐私与安全

- 登录状态和 Cookie 仅保存在使用者本地机器。
- `cookie.config` 已加入 `.gitignore`，不会被提交。
- 请勿分享 Cookie、登录二维码或含个人数据的日志与结果文件。
