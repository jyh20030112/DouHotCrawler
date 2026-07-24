#!/usr/bin/env bash
# Build a native desktop bundle. Run this on the target OS and architecture.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

uv run --no-sync --group build pyinstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name DouHotCrawler \
  --icon douhot_crawler/resources/logo.ico \
  --add-data "douhot_crawler/resources/logo.ico:douhot_crawler/resources" \
  --add-data "douhot_crawler/resources/logo.png:douhot_crawler/resources" \
  --specpath build \
  --workpath build/pyinstaller \
  --distpath dist \
  --paths . \
  --collect-all qfluentwidgets \
  --collect-all crawl4ai \
  --collect-all playwright \
  --hidden-import playwright.async_api \
  scripts/pyinstaller_gui.py
