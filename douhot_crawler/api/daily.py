from __future__ import annotations

import os
import sys

import httpx

# Importing core.config loads the project .env without overriding real environment.
from douhot_crawler.core import config as _core_config  # noqa: F401


def main() -> None:
    base_url = os.environ.get("DOUHOT_DAILY_API_URL", "http://127.0.0.1:8000").rstrip("/")
    url = f"{base_url}/api/v1/tasks/pipeline"
    try:
        response = httpx.post(url, json={}, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"创建每日流水线失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(
        f"task_id={payload['task_id']} status={payload['status']} "
        f"created={str(payload.get('created', True)).lower()}"
    )


if __name__ == "__main__":
    main()
