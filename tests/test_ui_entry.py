from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_ui_module_can_be_loaded_as_a_script_path(tmp_path: Path) -> None:
    """The documented ``uv run path/to/app.py`` form has no package context."""

    project_root = Path(__file__).resolve().parents[1]
    app_path = project_root / "douhot_crawler" / "ui" / "app.py"
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "DOUHOT_DATA_ROOT": str(tmp_path / "data"),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import runpy; "
                f"runpy.run_path({str(app_path)!r}, run_name='ui_import_smoke')"
            ),
        ],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_mcp_module_can_be_loaded_as_a_script_path(tmp_path: Path) -> None:
    """Direct execution must not let interfaces/mcp.py shadow the MCP SDK."""

    project_root = Path(__file__).resolve().parents[1]
    mcp_path = project_root / "douhot_crawler" / "interfaces" / "mcp.py"
    environment = os.environ.copy()
    environment.update(
        {
            "DOUHOT_DATA_ROOT": str(tmp_path / "data"),
            "DOUHOT_MCP_TOKEN": "test-only-token",
            "DOUHOT_DOWNLOAD_SECRET": "test-only-secret",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import runpy; "
                f"runpy.run_path({str(mcp_path)!r}, run_name='mcp_import_smoke')"
            ),
        ],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
