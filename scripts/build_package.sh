#!/usr/bin/env bash
# Build a native desktop bundle. Run this on the target OS and architecture.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

ICON_PATH="$PROJECT_DIR/douhot_crawler/resources/logo.ico"
LOGO_PATH="$PROJECT_DIR/douhot_crawler/resources/logo.png"

for resource in "$ICON_PATH" "$LOGO_PATH"; do
  if [[ ! -f "$resource" ]]; then
    echo "Required build resource not found: $resource" >&2
    exit 1
  fi
done

uv run --no-sync --group build pyinstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name DouHotCrawler \
  --icon "$ICON_PATH" \
  --add-data "$ICON_PATH:douhot_crawler/resources" \
  --add-data "$LOGO_PATH:douhot_crawler/resources" \
  --specpath build \
  --workpath build/pyinstaller \
  --distpath dist \
  --paths . \
  --collect-all qfluentwidgets \
  --collect-all crawl4ai \
  --collect-all playwright \
  --hidden-import playwright.async_api \
  scripts/pyinstaller_gui.py
