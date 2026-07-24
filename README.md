# DouHotCrawler

A desktop application for crawling the Douhot trending video board by keyword, saving results to Excel, and supplementing existing videos with transcript text.

No Python, uv, or other developer tools required — just download and run.

## System Requirements

- **OS**: Windows 10 or later, x86_64 (Intel / AMD)
- **Browser**: **Google Chrome** or **Microsoft Edge** must be installed

> The desktop bundle currently targets **Windows x86_64 only**. If Chrome or Edge is not detected, the app will prompt you to download Chromium as a fallback. For macOS / Linux, see [Running from Source](#running-from-source).

## Download

Go to the **Actions** tab on GitHub, open a successful "Package desktop application" workflow run, and download the `DouHotCrawler-windows-x86_64` artifact.

| Artifact | Platform |
|----------|----------|
| `DouHotCrawler-windows-x86_64` | Windows 10+ (Intel / AMD) |

## Quick Start

1. Extract the downloaded zip file.
2. Keep the entire `DouHotCrawler` folder intact — do not move the `.exe` out of it.
3. Launch `DouHotCrawler.exe`. The app will detect your system Chrome or Edge automatically.
4. If no system browser is found, click **"Download Browser"** in the "Browser Setup" card.
5. Once the browser is ready, click the status button in the **"Crawler Cookie"** card to open the Douhot login page. Scan the QR code, then click **"Done, Save Login"**.
6. (Optional) For transcript extraction, paste your full `www.douyin.com` cookie into the **"Transcript Cookie"** tab and save.

After the first run, subsequent launches typically won't need another browser download or re-login.

## Crawling Trending Videos

1. Open the **"热榜爬取"** (Trending Crawl) tab.
2. Enter a keyword, e.g. `美容` (beauty).
3. Pick a result type and time range.
4. Click **"开始爬取"** (Start Crawl).
5. Monitor progress in the log panel. Results are written to Excel incrementally.

When re-crawling the same keyword, existing videos are automatically skipped — ideal for ongoing data collection.

## Extracting Transcripts

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

### Windows says "unknown publisher"?

This is a standard warning for unsigned applications. Only proceed if you downloaded the artifact from a trusted source (your own GitHub Actions).

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
