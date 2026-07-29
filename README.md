# DouHotCrawler

A desktop application for crawling the Douhot trending video board by keyword, saving results to Excel, and supplementing existing videos with transcript text.

No Python, uv, or other developer tools required — just download and run.

## System Requirements

- **Browser**: **Google Chrome** or **Microsoft Edge** must be installed. Chromium can be downloaded from within the app if neither is available.

Choose the package that matches both your operating system and CPU:

| Package | Use it on |
| --- | --- |
| `DouHotCrawler-windows-x86_64.zip` | Windows 10 or later on Intel / AMD (x86_64) CPUs |
| `DouHotCrawler-macos-arm64.zip` | Apple Silicon Macs (M1 / M2 / M3 / M4) |
| `DouHotCrawler-Linux-x86_64.zip` | x86_64 Linux desktop systems; built on Ubuntu 24.04 |

- Windows on ARM and Intel-based Macs are not currently packaged.

## Download

For a tagged version, download the matching zip from the repository's **Releases** page. Builds from an in-progress change are available as artifacts in a successful **Package desktop application** GitHub Actions run.

## Install and Launch

1. Extract the downloaded zip; keep all extracted files together.
2. Start the application for your platform:

   | Platform | Launch command / action |
   | --- | --- |
   | Windows | Double-click `DouHotCrawler/DouHotCrawler.exe`. Do not move the `.exe` out of its folder. |
   | macOS (Apple Silicon) | Double-click `DouHotCrawler.app`. If macOS blocks an unsigned app, Control-click it, choose **Open**, then confirm. |
   | Linux x86_64 | Run `chmod +x DouHotCrawler/DouHotCrawler` once, then run `./DouHotCrawler/DouHotCrawler` from the extracted directory. |
3. The app detects Chrome or Edge automatically. If neither is found, click **"Download Browser"** in the Browser Setup card.
4. In the **Crawler Cookie** card, open the Douhot login page, scan the QR code, and click **"Done, Save Login"**.
5. (Optional) For transcript extraction, paste your full `www.douyin.com` cookie into the **Transcript Cookie** tab and save.

After the first run, subsequent launches typically won't need another browser download or re-login.

## Crawling Trending Videos

1. Open the **"热榜爬取"** (Trending Crawl) tab.
2. Enter a keyword, e.g. `美容` (beauty).
3. Pick a result type and time range.
4. Click **"开始爬取"** (Start Crawl).
5. Monitor progress in the log panel. Results are written to Excel incrementally.

When re-crawling the same keyword, existing videos are automatically skipped — ideal for ongoing data collection.

## Extracting Transcripts

Before using transcript extraction, create a local `.env` file containing your private extraction-service endpoint:

```bash
EXTRACT_API_URL=http://your-api-host:28600/api/v1/videos/extract
```

For the desktop package, place `.env` beside `DouHotCrawler.exe` / `DouHotCrawler` on Windows or Linux, or beside `DouHotCrawler.app` on macOS. For a source checkout, copy `.env.example` to `.env` in the project directory. `.env` is excluded from Git and must never be committed. A pre-set system environment variable takes precedence over `.env`.

1. Complete at least one crawl to generate a result Excel.
2. Open the **"口播提取"** (Transcript Extraction) tab.
3. Optionally specify sheet names, a processing limit, or a request interval.
4. Click **"开始提取口播"** (Start Extraction).

Records that already have transcripts are skipped by default. Check **"覆盖已有口播"** (Overwrite) to re-extract.

## Export

Click **"下载 Excel"** (Download Excel) in the header bar to export the result file to any location.

## FAQ

### Chrome or Edge not detected?

Make sure Google Chrome or Microsoft Edge is installed. If they are but detection still fails, click the browser status button to download Chromium instead.

### Chromium download fails?

Check your network connection, disk space, and proxy settings, then retry.

### Can't start crawling?

Confirm the "Browser Setup" card shows a ready status, and that the "Crawler Cookie" card shows a valid login.

### Transcript extraction fails?

Re-copy your full cookie from `www.douyin.com` and save it again. Cookies may expire due to logout, session expiry, or account changes.

### Windows or macOS blocks the app?

The packages are not code-signed. Only continue when you downloaded the zip from this repository's Release or Actions artifact. On macOS, Control-click the app, choose **Open**, and then confirm.

## Privacy & Security

- Login state and cookies are stored exclusively on your local machine.
- Never share or upload cookies, QR codes, result Excel files, or logs containing personal data.
- Ensure your usage complies with the relevant platform's terms of service.

## Running from Source

If you need to run on macOS or Linux, or prefer to work with the source directly:

```bash
# Prerequisites: Python 3.12+, uv
git clone <repo-url>
cd crael4i-demo
uv sync
uv run douhot-gui
```

The `uv run douhot-crawl` and `uv run douhot-login` CLI entry points are also available.

## License

This project is for personal use and educational purposes only.
