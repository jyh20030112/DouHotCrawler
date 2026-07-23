#!/usr/bin/env bash
# Launch douhot_gui with Xft-enabled Tcl/Tk 9.0.
#
# The uv-provided Python ships Tk built without fontconfig support ("no-xft"),
# which leaves only the "fixed" X11 core font — zero CJK glyphs.
# This wrapper preloads locally-built Tcl/Tk 9.0.3 compiled --enable-xft.
#
# Build artifacts live under $HOME/.local/lib and $HOME/.local/lib/tcl9.0 + tk9.0.
# To rebuild: see the project README or CLAUDE.md.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TCL_TK_PREFIX="${TCL_TK_PREFIX:-$HOME/.local}"

export LD_PRELOAD="${TCL_TK_PREFIX}/lib/libtcl9.0.so:${TCL_TK_PREFIX}/lib/libtcl9tk9.0.so"
export TCL_LIBRARY="${TCL_TK_PREFIX}/lib/tcl9.0"
export TK_LIBRARY="${TCL_TK_PREFIX}/lib/tk9.0"

exec python3 "$SCRIPT_DIR/douhot_gui.py" "$@"
