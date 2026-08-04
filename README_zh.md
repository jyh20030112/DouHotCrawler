# DouHotCrawler

中文 | [English](README.md)

DouHotCrawler 用于按关键词采集热点宝（Douhot）榜单视频，将结果增量保存到 Excel，并可通过独立配置的私有接口补全视频口播。桌面 GUI、命令行、FastAPI 任务服务和 Streamable HTTP MCP 服务共用同一套核心模块。

> 本项目会自动操作第三方网站，页面变更、账号状态、访问频率限制或平台规则都可能影响运行。请仅采集你有权访问和处理的数据。

## 主要功能

- 按关键词、榜单类型和时间范围采集视频。
- 将视频信息和高赞评论写入按关键词划分的 Excel Sheet。
- 自动跳过工作簿中已存在的视频，支持持续增量采集。
- 通过私有提取接口为已有记录补充口播文本。
- 安全检查爬虫登录态和口播 Cookie 状态，不输出 Cookie 内容。
- 提供桌面 GUI、CLI 和带 Bearer 认证的 MCP 服务。
- 提供无认证的 FastAPI FIFO 任务队列，支持爬取、口播、完整流水线及安全暂停/恢复。
- 使用 PyInstaller 构建 Windows、macOS 和 Linux 原生桌面包。

## 环境要求

使用发布包只需受支持的桌面系统，以及 Google Chrome 或 Microsoft Edge；若未安装，程序可下载 Playwright Chromium。

| 安装包 | 适用平台 |
| --- | --- |
| `DouHotCrawler-windows-x86_64.zip` | Windows 10 及以上，Intel/AMD 处理器 |
| `DouHotCrawler-macos-arm64.zip` | Apple Silicon macOS |
| `DouHotCrawler-Linux-x86_64.zip` | x86_64 Linux 桌面系统 |

源码运行需要 Python 3.12+、[uv](https://docs.astral.sh/uv/) 和 Git。

## 快速开始

### 桌面安装包

1. 从 Releases 或成功的 **Package desktop application** 工作流下载对应压缩包。
2. 完整解压，不要单独移动主程序。
3. Windows 启动 `DouHotCrawler.exe`，macOS 启动 `DouHotCrawler.app`，Linux 运行 `./DouHotCrawler/DouHotCrawler`。
4. 确认“浏览器准备”显示可用；需要时点击“下载浏览器”。
5. 打开爬虫登录流程，扫码后保存登录状态。
6. 在“热榜爬取”页面填写关键词并开始采集。

当前发布包未进行代码签名。macOS 可按住 Control 点击应用后选择“打开”。只有在确认文件来自可信的项目 Release 或 Actions 构建产物时，才应跳过系统警告。

### 源码运行

```bash
git clone <repo-url>
cd crael4i-demo
uv sync
cp .env.example .env
uv run douhot-gui
```

`.env` 可能包含私有接口和密钥，已被 Git 忽略。

## 使用方式

### 桌面 GUI

- **热榜爬取**：设置关键词、榜单类型和时间范围；日志会显示进度，记录按页增量保存。
- **口播提取**：可选择 Sheet、数量限制及是否覆盖；默认保留已有口播。
- **下载 Excel**：将当前结果工作簿导出到指定位置。
- **安全停止**：完成当前记录并保存后停止任务。

### 命令行

```bash
# 扫码登录并保存热点宝浏览器 Profile
uv run douhot-login

# 采集关键词
uv run douhot-crawl "美容" \
  --result-type "视频总榜" \
  --time-range "近7天"

# 为工作簿补充口播
uv run douhot-analyze --limit 20
```

使用 `--help` 查看各命令的完整参数。`python -m douhot_crawler` 等价于 `douhot-crawl`。

### 配置口播提取服务

在项目根目录的 `.env` 中设置私有接口：

```dotenv
EXTRACT_API_URL=http://your-api-host:28600/api/v1/videos/extract
```

桌面发布包将 `.env` 放在可执行文件或 `.app` 旁。GUI 会把抖音 Cookie 保存在系统应用数据目录；请勿提交或分享该文件。

### MCP 服务

至少配置访问令牌和下载签名密钥：

```bash
cp .env.example .env
# 修改 DOUHOT_MCP_TOKEN、DOUHOT_DOWNLOAD_SECRET 和 EXTRACT_API_URL
uv run douhot-mcp
```

默认端点为 `http://127.0.0.1:8765/mcp`，请求需携带 `Authorization: Bearer <DOUHOT_MCP_TOKEN>`。服务支持健康检查、扫码登录、爬取、批量分析、任务查询/等待/取消、候选视频列表、单条口播提取和签名下载。数据按可信 `user_id` 的哈希隔离，下载链接 15 分钟后失效。

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DOUHOT_MCP_TOKEN` | 必填 | MCP Bearer Token |
| `DOUHOT_MCP_HOST` | `127.0.0.1` | 监听地址 |
| `DOUHOT_MCP_PORT` | `8765` | 监听端口 |
| `DOUHOT_PUBLIC_URL` | `http://127.0.0.1:8765` | 签名下载链接的基础地址 |
| `DOUHOT_DOWNLOAD_SECRET` | 部署时必须修改 | 下载链接 HMAC 密钥 |
| `DOUHOT_DATA_ROOT` | 系统应用数据目录 | MCP 任务、Profile 和工作簿目录 |
| `DOUHOT_LOGIN_TIMEOUT_SECONDS` | `300` | 扫码登录超时秒数 |
| `DOUHOT_COOKIE_SOURCE` | 项目 `cookie.config` | 可选的初始口播 Cookie 来源 |

不要使用示例密钥将服务暴露到公网；监听非本机地址时，应在服务前增加 TLS 和必要的访问控制。

### FastAPI 任务服务

先复制 `.env.example`，填写三个外部接口、口播接口、热点 `openId` 和 API 数据目录。默认使用 `DOUHOT_API_DATA_ROOT=data/api`，相对路径以服务启动时的工作目录为基准；本机和服务器均可复用，不需要写死用户名。配置缺失时服务会拒绝启动。

```bash
uv sync
uv run douhot-api
```

默认监听 `127.0.0.1:8000`，固定为单 Uvicorn worker，接口本身不做身份认证。交互文档位于 `http://127.0.0.1:8000/docs`。任务采用 SQLite 持久化的全局 FIFO 队列，同一时间只运行一个爬取、口播或流水线任务；Cookie 每个阶段从配置接口重新读取，只保存在内存中。

主要接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 数据库、worker 和浏览器状态 |
| `GET` | `/api/v1/keywords` | 返回 `{"key_word": [...]}` 热点关键词 |
| `POST` | `/api/v1/tasks/crawl` | 创建单关键词爬取任务，默认最多 500 条 |
| `POST` | `/api/v1/tasks/analyze` | 为已成功的爬取任务补充口播 |
| `POST` | `/api/v1/tasks/pipeline` | 顺序执行关键词获取、爬取、口播和发送 |
| `POST` | `/api/v1/tasks/{task_id}/pause` | 在当前安全检查点暂停 |
| `POST` | `/api/v1/tasks/{task_id}/resume` | 恢复 paused 任务 |
| `GET` | `/api/v1/tasks/{task_id}` | 查询状态、进度、告警与结果文件信息 |

不传 `keywords` 时流水线读取全部热点关键词（默认 30 个）；也可传入不超过 30 个关键词覆盖。发送阶段跳过缺少视频名称、URL、博主或口播的行，每 20 条一批；粉丝数会转换为整数，无法解析时按 `0` 发送并记录告警。Excel、任务日志保留 3 天，SQLite 元数据保留 7 天，运行中或暂停中的任务不会清理。

每天上海时区凌晨 3 点可通过 cron 调用轻量脚本。它只创建任务、输出 `task_id` 后退出；已有 active/paused 流水线时服务返回原任务，不重复创建。

```cron
CRON_TZ=Asia/Shanghai
0 3 * * * cd /absolute/path/to/crael4i-demo && /absolute/path/to/uv run douhot-daily >> /var/log/douhot-daily.log 2>&1
```

## 项目架构

源码按职责拆分，依赖方向收敛到 `core`，GUI 和外部协议入口位于边缘层：

```text
crael4i-demo/
├── douhot_crawler/
│   ├── core/             # 配置、共享模型、Excel 持久化
│   ├── browser/          # 浏览器检测、Playwright 补丁、登录、Cookie
│   ├── crawling/         # 页面交互、内容采集、爬取编排
│   ├── transcript/       # 口播接口客户端与 Cookie 管理
│   ├── api/              # FastAPI、SQLite FIFO、流水线与外部接口客户端
│   ├── services/         # 多用户任务生命周期与签名下载
│   ├── interfaces/       # 爬取/登录 CLI 与 MCP
│   ├── ui/               # Qt 桌面应用、设置和资源
│   └── __main__.py       # `python -m douhot_crawler` 入口
├── tests/                # 单元测试和异步服务测试
├── scripts/              # GUI 启动和 PyInstaller 构建脚本
├── .github/workflows/    # 测试、打包和发布自动化
└── pyproject.toml        # 项目元数据、依赖和命令入口
```

主要调用链：

```text
GUI / CLI / MCP
       │
       ├── crawling ── browser 自动化 ── 热点宝
       │       └── core/storage ── Excel
       └── transcript ── 私有口播提取接口

MCP ── services/jobs ── 用户隔离的 Profile、任务、Excel、签名下载

FastAPI ── api/service ── SQLite FIFO ── 每关键词：爬取 → 口播 → 20 条/批发送
```

## 本地数据位置

默认运行数据不会写入源码目录：

| 平台 | 数据目录 |
| --- | --- |
| Windows | `%LOCALAPPDATA%/DouHotCrawler` |
| macOS | `~/Library/Application Support/DouHotCrawler` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/DouHotCrawler` |

爬虫浏览器 Profile 位于 `~/.crawl4ai/profiles/douhot`。不要上传或分享 Profile、Cookie、工作簿、登录二维码，以及包含个人信息的日志。

## 开发与打包

```bash
# 安装运行和开发依赖
uv sync

# 运行全部测试
uv run pytest -q

# 为当前系统和架构构建桌面包
uv sync --group build
bash scripts/build_package.sh
```

构建产物位于 `dist/`。代码规范和 PR 流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 使用边界

本项目仅用于个人学习和经授权的数据采集。使用者需自行遵守平台规则、适用法律、账号权限和数据保护要求。
