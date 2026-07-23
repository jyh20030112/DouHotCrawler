#!/usr/bin/env bash
# Build a native desktop bundle. Run this on the target OS and architecture.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

uv run --group build pyinstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name DouHotCrawler \
  --specpath build \
  --workpath build/pyinstaller \
  --distpath dist \
  --paths . \
  --collect-all qfluentwidgets \
  --collect-all crawl4ai \
  --collect-all playwright \
  --hidden-import playwright.async_api \
  scripts/pyinstaller_gui.py
