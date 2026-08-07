from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .errors import ApiError
from .models import ACTIVE_PIPELINE_STATUSES, TaskKind, TaskStatus


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ApiTaskStore:
    """Durable global FIFO queue and pipeline checkpoints."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    phase TEXT,
                    params_json TEXT NOT NULL,
                    progress_json TEXT NOT NULL DEFAULT '{}',
                    artifact_path TEXT,
                    result_json TEXT,
                    error TEXT,
                    warning_count INTEGER NOT NULL DEFAULT 0,
                    pause_requested INTEGER NOT NULL DEFAULT 0,
                    pause_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS tasks_queue_idx
                    ON tasks(status, created_at);

                CREATE TABLE IF NOT EXISTS pipeline_keywords (
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    source TEXT NOT NULL DEFAULT 'hotspot',
                    keyword TEXT NOT NULL,
                    sheet_name TEXT,
                    crawl_done INTEGER NOT NULL DEFAULT 0,
                    analyze_done INTEGER NOT NULL DEFAULT 0,
                    upload_done INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    PRIMARY KEY(task_id, position)
                );

                CREATE TABLE IF NOT EXISTS deliveries (
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    keyword TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    sent_at TEXT,
                    last_error TEXT,
                    PRIMARY KEY(task_id, keyword, video_url, payload_hash)
                );
                """
            )
            checkpoint_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(pipeline_keywords)"
                ).fetchall()
            }
            if "source" not in checkpoint_columns:
                connection.execute(
                    "ALTER TABLE pipeline_keywords "
                    "ADD COLUMN source TEXT NOT NULL DEFAULT 'hotspot'"
                )
            if "sheet_name" not in checkpoint_columns:
                connection.execute(
                    "ALTER TABLE pipeline_keywords ADD COLUMN sheet_name TEXT"
                )
            connection.execute(
                "UPDATE pipeline_keywords SET sheet_name=keyword "
                "WHERE sheet_name IS NULL OR sheet_name=''"
            )
            interrupted = connection.execute(
                "SELECT id, kind FROM tasks WHERE status IN (?, ?)",
                (TaskStatus.RUNNING, TaskStatus.PAUSING),
            ).fetchall()
            timestamp = utc_now()
            for row in interrupted:
                if row["kind"] == TaskKind.PIPELINE:
                    connection.execute(
                        "UPDATE tasks SET status=?, pause_requested=0, "
                        "pause_reason='shutdown', updated_at=? WHERE id=?",
                        (TaskStatus.QUEUED, timestamp, row["id"]),
                    )
                else:
                    connection.execute(
                        "UPDATE tasks SET status=?, error=?, finished_at=?, "
                        "updated_at=? WHERE id=?",
                        (
                            TaskStatus.FAILED,
                            "服务重启，手动任务已终止",
                            timestamp,
                            timestamp,
                            row["id"],
                        ),
                    )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["task_id"] = result.pop("id")
        result["params"] = json.loads(result.pop("params_json"))
        result["progress"] = json.loads(result.pop("progress_json") or "{}")
        raw_result = result.pop("result_json")
        result["result"] = json.loads(raw_result) if raw_result else None
        result["pause_requested"] = bool(result["pause_requested"])
        artifact = result.pop("artifact_path")
        if artifact and result["result"] and "artifact" in result["result"]:
            result["artifact"] = result["result"]["artifact"]
        else:
            result["artifact"] = None
        return result

    def create(self, kind: TaskKind, params: dict[str, Any]) -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        timestamp = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO tasks "
                "(id, kind, status, params_json, progress_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, '{}', ?, ?)",
                (
                    task_id,
                    kind,
                    TaskStatus.QUEUED,
                    json.dumps(params, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise ApiError("TASK_NOT_FOUND", "任务不存在", status_code=404)
        return self._decode(row)

    def active_pipeline(self) -> dict[str, Any] | None:
        placeholders = ", ".join("?" for _ in ACTIVE_PIPELINE_STATUSES)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM tasks WHERE kind=? AND status IN ({placeholders}) "
                "ORDER BY created_at LIMIT 1",
                (TaskKind.PIPELINE, *ACTIVE_PIPELINE_STATUSES),
            ).fetchone()
        return self._decode(row) if row else None

    def claim_next(self) -> dict[str, Any] | None:
        timestamp = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM tasks WHERE status=? ORDER BY created_at LIMIT 1",
                (TaskStatus.QUEUED,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE tasks SET status=?, started_at=COALESCE(started_at, ?), "
                "updated_at=?, pause_reason=NULL WHERE id=? AND status=?",
                (
                    TaskStatus.RUNNING,
                    timestamp,
                    timestamp,
                    row["id"],
                    TaskStatus.QUEUED,
                ),
            )
        return self.get(row["id"])

    def update(self, task_id: str, **values: Any) -> dict[str, Any]:
        allowed = {
            "status",
            "phase",
            "progress_json",
            "artifact_path",
            "result_json",
            "error",
            "warning_count",
            "pause_requested",
            "pause_reason",
            "started_at",
            "finished_at",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"不支持更新任务字段：{sorted(unknown)}")
        values["updated_at"] = utc_now()
        serialized: list[Any] = []
        for key, value in values.items():
            if key in {"progress_json", "result_json"} and value is not None:
                value = json.dumps(value, ensure_ascii=False)
            if key == "pause_requested":
                value = int(bool(value))
            serialized.append(value)
        assignments = ", ".join(f"{key}=?" for key in values)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE tasks SET {assignments} WHERE id=?",
                (*serialized, task_id),
            )
            if cursor.rowcount != 1:
                raise ApiError("TASK_NOT_FOUND", "任务不存在", status_code=404)
        return self.get(task_id)

    def update_progress(
        self, task_id: str, *, phase: str | None = None, **progress: Any
    ) -> dict[str, Any]:
        current = self.get(task_id)
        merged = {**current["progress"], **progress}
        values: dict[str, Any] = {"progress_json": merged}
        if phase is not None:
            values["phase"] = phase
        return self.update(task_id, **values)

    def add_warning(self, task_id: str, message: str) -> None:
        current = self.get(task_id)
        progress = current["progress"]
        warnings = list(progress.get("warnings", []))
        warnings.append(message)
        progress["warnings"] = warnings[-100:]
        self.update(
            task_id,
            progress_json=progress,
            warning_count=current["warning_count"] + 1,
        )

    def request_pause(self, task_id: str) -> dict[str, Any]:
        task = self.get(task_id)
        status = TaskStatus(task["status"])
        if status == TaskStatus.PAUSED:
            return task
        if status == TaskStatus.QUEUED:
            return self.update(
                task_id,
                status=TaskStatus.PAUSED,
                pause_requested=False,
                pause_reason="user",
            )
        if status == TaskStatus.RUNNING:
            return self.update(
                task_id,
                status=TaskStatus.PAUSING,
                pause_requested=True,
                pause_reason="user",
            )
        if status == TaskStatus.PAUSING:
            return task
        raise ApiError(
            "TASK_STATE_CONFLICT",
            f"状态为 {status} 的任务不能暂停",
            status_code=409,
        )

    def resume(self, task_id: str) -> dict[str, Any]:
        task = self.get(task_id)
        if task["status"] != TaskStatus.PAUSED:
            raise ApiError(
                "TASK_STATE_CONFLICT",
                "只有 paused 任务可以恢复",
                status_code=409,
            )
        return self.update(
            task_id,
            status=TaskStatus.QUEUED,
            pause_requested=False,
            pause_reason=None,
            error=None,
            finished_at=None,
        )

    def should_pause(self, task_id: str) -> bool:
        return self.get(task_id)["pause_requested"]

    def request_worker_shutdown(self) -> None:
        """Ask the single running task to stop at its next safe checkpoint."""

        timestamp = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status=?, pause_requested=1, "
                "pause_reason='shutdown', updated_at=? WHERE status=?",
                (TaskStatus.PAUSING, timestamp, TaskStatus.RUNNING),
            )

    def finish(
        self,
        task_id: str,
        *,
        result: dict[str, Any],
        artifact_path: Path | None,
    ) -> dict[str, Any]:
        current = self.get(task_id)
        status = (
            TaskStatus.SUCCEEDED_WITH_WARNINGS
            if current["warning_count"]
            else TaskStatus.SUCCEEDED
        )
        timestamp = utc_now()
        return self.update(
            task_id,
            status=status,
            result_json=result,
            artifact_path=str(artifact_path) if artifact_path else None,
            pause_requested=False,
            finished_at=timestamp,
        )

    def fail(self, task_id: str, message: str) -> dict[str, Any]:
        return self.update(
            task_id,
            status=TaskStatus.FAILED,
            error=message,
            pause_requested=False,
            finished_at=utc_now(),
        )

    def mark_paused(self, task_id: str, reason: str) -> dict[str, Any]:
        return self.update(
            task_id,
            status=TaskStatus.PAUSED,
            pause_requested=False,
            pause_reason=reason,
        )

    def set_pipeline_keywords(
        self,
        task_id: str,
        keywords: list[str | dict[str, str]],
    ) -> None:
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT COUNT(*) FROM pipeline_keywords WHERE task_id=?",
                (task_id,),
            ).fetchone()[0]
            if existing:
                return
            rows = []
            for index, item in enumerate(keywords):
                if isinstance(item, str):
                    source = "hotspot"
                    keyword = item
                    sheet_name = item
                else:
                    source = item["source"]
                    keyword = item["keyword"]
                    sheet_name = item["sheet_name"]
                rows.append((task_id, index, source, keyword, sheet_name))
            connection.executemany(
                "INSERT INTO pipeline_keywords"
                "(task_id, position, source, keyword, sheet_name) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def pipeline_keywords(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pipeline_keywords WHERE task_id=? ORDER BY position",
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_pipeline_keyword(
        self, task_id: str, position: int, **values: Any
    ) -> None:
        allowed = {"crawl_done", "analyze_done", "upload_done", "last_error"}
        if set(values) - allowed:
            raise ValueError("不支持的关键词检查点字段")
        assignments = ", ".join(f"{key}=?" for key in values)
        serialized = [
            int(value) if key.endswith("_done") else value
            for key, value in values.items()
        ]
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE pipeline_keywords SET {assignments} "
                "WHERE task_id=? AND position=?",
                (*serialized, task_id, position),
            )

    def delivery_sent(
        self, task_id: str, keyword: str, video_url: str, payload_hash: str
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM deliveries WHERE task_id=? AND keyword=? "
                "AND video_url=? AND payload_hash=?",
                (task_id, keyword, video_url, payload_hash),
            ).fetchone()
        return bool(row and row["status"] == "sent")

    def mark_deliveries_sent(
        self, task_id: str, rows: list[tuple[str, str, str]]
    ) -> None:
        timestamp = utc_now()
        with self._lock, self._connect() as connection:
            connection.executemany(
                "INSERT INTO deliveries "
                "(task_id, keyword, video_url, payload_hash, status, attempts, sent_at) "
                "VALUES (?, ?, ?, ?, 'sent', 1, ?) "
                "ON CONFLICT(task_id, keyword, video_url, payload_hash) DO UPDATE SET "
                "status='sent', attempts=deliveries.attempts+1, sent_at=excluded.sent_at, "
                "last_error=NULL",
                [
                    (task_id, keyword, video_url, payload_hash, timestamp)
                    for keyword, video_url, payload_hash in rows
                ],
            )

    def mark_deliveries_failed(
        self,
        task_id: str,
        rows: list[tuple[str, str, str]],
        error: str,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.executemany(
                "INSERT INTO deliveries "
                "(task_id, keyword, video_url, payload_hash, status, attempts, last_error) "
                "VALUES (?, ?, ?, ?, 'failed', 4, ?) "
                "ON CONFLICT(task_id, keyword, video_url, payload_hash) DO UPDATE SET "
                "status='failed', attempts=deliveries.attempts+4, "
                "last_error=excluded.last_error",
                [
                    (task_id, keyword, video_url, payload_hash, error)
                    for keyword, video_url, payload_hash in rows
                ],
            )

    def cleanup_metadata(self, retention_days: int) -> list[str]:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        terminal = (
            TaskStatus.SUCCEEDED,
            TaskStatus.SUCCEEDED_WITH_WARNINGS,
            TaskStatus.FAILED,
        )
        placeholders = ", ".join("?" for _ in terminal)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"SELECT id FROM tasks WHERE status IN ({placeholders}) "
                "AND updated_at < ?",
                (*terminal, cutoff),
            ).fetchall()
            ids = [row["id"] for row in rows]
            connection.executemany("DELETE FROM tasks WHERE id=?", [(item,) for item in ids])
        return ids

    def old_artifact_task_ids(self, retention_days: int) -> list[str]:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id FROM tasks WHERE status IN (?, ?, ?) AND updated_at < ?",
                (
                    TaskStatus.SUCCEEDED,
                    TaskStatus.SUCCEEDED_WITH_WARNINGS,
                    TaskStatus.FAILED,
                    cutoff,
                ),
            ).fetchall()
        return [row["id"] for row in rows]

    def ping(self) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1").fetchone()[0] == 1
