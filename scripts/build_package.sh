#!/usr/bin/env bash
# Build a native desktop bundle. Run this on the target OS and architecture.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

ICON_RELATIVE_PATH="douhot_crawler/ui/resources/favicon.ico"

if [[ ! -f "$ICON_RELATIVE_PATH" ]]; then
  echo "Required build resource not found: $ICON_RELATIVE_PATH" >&2
  exit 1
fi

# Git Bash rewrites colon-separated arguments before invoking Windows programs.
if [[ -n "${MSYSTEM:-}" ]]; then
  export MSYS2_ARG_CONV_EXCL="*"
  ICON_PATH="$(pwd -W)/$ICON_RELATIVE_PATH"
else
  ICON_PATH="$PROJECT_DIR/$ICON_RELATIVE_PATH"
fi

uv run --no-sync --group build pyinstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name DouHotCrawler \
  --icon "$ICON_PATH" \
  --add-data "$ICON_PATH:douhot_crawler/ui/resources" \
  --specpath build \
  --workpath build/pyinstaller \
  --distpath dist \
  --paths . \
  --additional-hooks-dir scripts/pyinstaller_hooks \
  --collect-all qfluentwidgets \
  --collect-all crawl4ai \
  --collect-all playwright \
  --hidden-import playwright.async_api \
  --exclude-module patchright \
  --exclude-module scipy \
  --exclude-module nltk \
  --exclude-module transformers \
  --exclude-module tokenizers \
  --exclude-module huggingface_hub \
  --exclude-module hf_xet \
  scripts/pyinstaller_gui.py
