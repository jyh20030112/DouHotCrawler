#!/usr/bin/env bash
# Launch the Fluent desktop GUI with the project's uv-managed environment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"
exec uv run douhot-gui "$@"
