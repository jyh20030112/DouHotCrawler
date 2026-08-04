# DouHotCrawler

[中文文档](README_zh.md) | English

DouHotCrawler collects keyword-based trending video data from Douhot (热点宝), stores results incrementally in Excel, and can enrich saved videos with transcript text. It provides a Qt desktop app, command-line tools, a FastAPI task service, and a Streamable HTTP MCP service backed by the same application modules.

> This project automates a third-party website. Page changes, account state, rate limits, or platform policy may affect it. Use it only with accounts and data you are authorized to access.

## Features

- Search by keyword, result type, and time range.
- Collect video metadata and top comments into per-keyword Excel sheets.
- Skip videos already present in the workbook for incremental collection.
- Extract transcripts through a separately configured private API.
- Inspect crawler and transcript-cookie status without logging cookie values.
- Run through a desktop GUI, CLI, or authenticated MCP endpoint.
- Run crawl, analysis, and end-to-end jobs through a durable single-worker FastAPI queue with safe pause/resume.
- Package native Windows, macOS, and Linux desktop bundles with PyInstaller.

## Requirements

For a release package, only a supported desktop OS and Google Chrome or Microsoft Edge are required. The app can download Playwright Chromium when neither browser is available.

| Artifact | Platform |
| --- | --- |
| `DouHotCrawler-windows-x86_64.zip` | Windows 10+ on Intel/AMD |
| `DouHotCrawler-macos-arm64.zip` | Apple Silicon macOS |
| `DouHotCrawler-Linux-x86_64.zip` | x86_64 Linux desktop |

Running from source requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and Git.

## Quick Start

### Desktop package

1. Download the matching archive from Releases or a successful **Package desktop application** workflow run.
2. Extract the entire archive and keep its files together.
3. Launch `DouHotCrawler.exe` on Windows, `DouHotCrawler.app` on macOS, or `./DouHotCrawler/DouHotCrawler` on Linux.
4. Confirm the Browser Setup card is ready. Use **Download Browser** if needed.
5. Open the crawler-login flow, scan the QR code, then save the login.
6. Enter a keyword on the Trending Crawl page and start collecting.

The distributed applications are not code-signed. On macOS, Control-click the app and choose **Open**. Only bypass an operating-system warning when the archive came from a trusted project release or workflow artifact.

### From source

```bash
git clone <repo-url>
cd crael4i-demo
uv sync
cp .env.example .env
uv run douhot-gui
```

The `.env` file may contain private endpoints and secrets and is ignored by Git.

## Usage

### Desktop GUI

The desktop app exposes two main workflows:

- **Trending Crawl**: choose a keyword, ranking type, and time range; progress is written to the log and records are saved incrementally.
- **Transcript Extraction**: select sheets or a processing limit, then fill missing transcript cells. Existing transcripts are preserved unless overwrite is enabled.

Use **Download Excel** to export the current workbook. A safe stop completes the current record before saving.

### CLI

```bash
# Log in and persist the Douhot browser profile
uv run douhot-login

# Crawl a keyword
uv run douhot-crawl "美容" \
  --result-type "视频总榜" \
  --time-range "近7天"

# Add transcripts to the saved workbook
uv run douhot-analyze --limit 20
```

Run any command with `--help` for all options. `python -m douhot_crawler` is equivalent to `douhot-crawl`.

### Transcript service

Transcript extraction requires a private API endpoint:

```dotenv
EXTRACT_API_URL=http://your-api-host:28600/api/v1/videos/extract
```

In the desktop package, place `.env` beside the executable/app bundle. In a source checkout, keep it in the project root. The GUI stores the Douyin cookie in the platform-specific application data directory; never commit or share it.

### MCP service

Configure at least an authentication token and a download-signing secret:

```bash
cp .env.example .env
# Edit DOUHOT_MCP_TOKEN, DOUHOT_DOWNLOAD_SECRET, and EXTRACT_API_URL
uv run douhot-mcp
```

The default endpoint is `http://127.0.0.1:8765/mcp` and requires `Authorization: Bearer <DOUHOT_MCP_TOKEN>`. The service provides health, QR login, crawl, analysis, job status/wait/cancel, video listing, single-transcript extraction, and signed downloads. Data is isolated by a hash of the trusted `user_id`; signed download links expire after 15 minutes.

Relevant environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DOUHOT_MCP_TOKEN` | required | Bearer token for MCP requests |
| `DOUHOT_MCP_HOST` | `127.0.0.1` | Bind address |
| `DOUHOT_MCP_PORT` | `8765` | Bind port |
| `DOUHOT_PUBLIC_URL` | `http://127.0.0.1:8765` | Base URL used in signed links |
| `DOUHOT_DOWNLOAD_SECRET` | required for deployment | HMAC secret for downloads |
| `DOUHOT_DATA_ROOT` | platform app-data directory | MCP jobs, profiles, and workbooks |
| `DOUHOT_LOGIN_TIMEOUT_SECONDS` | `300` | QR-login timeout |
| `DOUHOT_COOKIE_SOURCE` | project `cookie.config` | Optional initial transcript-cookie source |

Do not expose the service publicly with placeholder secrets. Put TLS and any additional access controls in front of it when binding beyond localhost.

### FastAPI task service

Copy `.env.example` and configure the full external-service URLs and hotspot `openId`. `DOUHOT_API_DATA_ROOT=data/api` is resolved from the service working directory, so it is portable between local and server deployments.

```bash
uv sync
uv run douhot-api
```

The unauthenticated service defaults to `127.0.0.1:8000` with exactly one Uvicorn worker. OpenAPI documentation is available at `/docs`. Its `/api/v1` routes provide health and keyword lookup plus crawl, transcript-analysis, standalone existing-Excel upload, pipeline, pause, resume, and task-status operations. Jobs use a persistent global FIFO queue. Pipeline jobs process keywords sequentially as crawl → transcript → upload, default to 3 videos per keyword (`DOUHOT_MAX_VIDEOS_PER_KEYWORD`, range 1–500), send eligible rows in batches of 20, and can resume from SQLite checkpoints. Cookies are fetched immediately before each relevant phase and are never persisted by the API.

Daily scheduling is built into the FastAPI process, so cron is not required. Configure it in `.env`; the time is interpreted in `Asia/Shanghai`:

```dotenv
DOUHOT_DAILY_ENABLED=true
DOUHOT_DAILY_TIME=03:00
```

Keep `uv run douhot-api` running. At the configured time it submits a pipeline, reusing any existing active or paused pipeline instead of creating a duplicate. Restart FastAPI after changing the schedule. `uv run douhot-daily` remains available as an immediate manual trigger.

## Architecture

The package is organized by responsibility. Dependencies point inward toward `core`; external entry points live in `interfaces` and `ui`.

```text
crael4i-demo/
├── douhot_crawler/
│   ├── core/             # Configuration, shared models, Excel persistence
│   ├── browser/          # Browser discovery, Playwright patch, login, cookies
│   ├── crawling/         # Page actions, collection, crawl orchestration
│   ├── transcript/       # Transcript API client and cookie management
│   ├── api/              # FastAPI, SQLite FIFO, pipeline, external clients
│   ├── services/         # Multi-user job lifecycle and signed downloads
│   ├── interfaces/       # Crawl/login CLI and Streamable HTTP MCP
│   ├── ui/               # Qt desktop app, settings, and bundled resources
│   └── __main__.py       # `python -m douhot_crawler`
├── tests/                # Unit and async service tests
├── scripts/              # GUI launcher and PyInstaller build tooling
├── .github/workflows/    # Test, package, and release automation
└── pyproject.toml        # Package metadata, dependencies, entry points
```

Runtime flow:

```text
GUI / CLI / MCP
       │
       ├── crawling ── browser automation ── Douhot
       │       └── core storage ── Excel
       └── transcript ── private extraction API

MCP ── services/jobs ── per-user profiles, jobs, Excel, signed downloads

FastAPI ── api/service ── SQLite FIFO ── per keyword: crawl → transcript → upload
```

## Local Data

By default, generated data is kept outside the source tree:

| Platform | Data directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%/DouHotCrawler` |
| macOS | `~/Library/Application Support/DouHotCrawler` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/DouHotCrawler` |

The crawler browser profile remains under `~/.crawl4ai/profiles/douhot`. Do not upload profiles, cookies, workbooks, QR codes, or logs containing personal data.

## Development

```bash
# Install runtime and development dependencies
uv sync

# Run the full test suite
uv run pytest -q

# Build a native bundle for the current OS/architecture
uv sync --group build
bash scripts/build_package.sh
```

The build output is written to `dist/`. See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions and pull-request guidance.

## License and Responsible Use

This project is intended for personal study and authorized data collection. You are responsible for complying with platform terms, applicable law, account permissions, and data-protection requirements.
