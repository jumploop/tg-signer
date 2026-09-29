import contextlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional


@dataclass
class SignRecordGroup:
    task_name: str
    user_id: Optional[str]
    records: list[tuple[str, str]]


@dataclass
class RecentSignRecord:
    task_name: str
    user_id: str
    sign_date: str
    signed_at: str
    account: Optional[str]
    source: str


@dataclass
class MigrationSummary:
    migrated_files: int = 0
    migrated_records: int = 0
    removed_files: int = 0
    skipped_files: list[Path] = field(default_factory=list)


class SignRecordStore:
    DB_FILENAME = "data.sqlite3"
    SCHEMA_VERSION = 1
    # sqlite3 默认只等 5s 就抛 `database is locked`;WebUI 进程与多个任务子进程
    # 会同时读写同一份 data.sqlite3,冷启动建 schema 时这点时间远远不够。
    BUSY_TIMEOUT_SECONDS = 30.0

    def __init__(self, workdir: str | Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self.workdir / self.DB_FILENAME

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.BUSY_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={int(self.BUSY_TIMEOUT_SECONDS * 1000)}")
        self._enable_wal(conn)
        self._ensure_schema(conn)
        return conn

    @contextlib.contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """打开一个用完即关的连接,事务语义与 `with conn` 一致。

        `with sqlite3.connect(...) as conn` 只提交/回滚事务,**不关闭连接**。
        所有调用点过去都写成 `with self._connect() as conn:`,于是每个连接
        都要等 gc 兜底才释放:实测 30 次 upsert 后仍有 30 个连接存活。单次
        调用看不出问题,但 8 个线程 x 200 轮时会同时压着大量已打开的库与
        WAL/-shm 句柄。这里把「事务 + 关闭」收敛成唯一入口,调用点不再重复
        承担关闭责任。
        """
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _enable_wal(conn: sqlite3.Connection) -> None:
        """尽力把日志模式切到 WAL(单写多读,跨进程友好)。

        多个连接同时从 delete 模式切向 WAL 时,SQLite 对失败者会**直接返回
        SQLITE_BUSY 而不调用 busy handler**,所以并发冷启动必然有输家。这里容忍
        失败:下一次连接会重试,期间的并发由 busy_timeout 兜底。
        """
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        version = self._get_schema_version(conn)
        if version >= self.SCHEMA_VERSION:
            return

        # Keep schema management lightweight, but make migrations explicit so
        # future schema changes can be appended as v2/v3 steps instead of
        # rewriting the bootstrap logic.
        migrations = {
            1: self._migrate_to_v1,
        }
        for target_version in range(version + 1, self.SCHEMA_VERSION + 1):
            migration = migrations.get(target_version)
            if migration is None:
                raise RuntimeError(f"Missing schema migration for v{target_version}")
            migration(conn)
            self._set_schema_version(conn, target_version)
        conn.commit()

    @staticmethod
    def _get_schema_version(conn: sqlite3.Connection) -> int:
        return conn.execute("PRAGMA user_version").fetchone()[0]

    @staticmethod
    def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
        conn.execute(f"PRAGMA user_version = {version}")

    @staticmethod
    def _migrate_to_v1(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sign_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name TEXT NOT NULL,
                user_id TEXT NOT NULL,
                sign_date TEXT NOT NULL,
                signed_at TEXT NOT NULL,
                account TEXT,
                source TEXT NOT NULL DEFAULT 'runtime',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_name, user_id, sign_date)
            );

            CREATE INDEX IF NOT EXISTS idx_sign_records_task_user_date
            ON sign_records(task_name, user_id, sign_date);
            """
        )

    def _upsert_records(
        self,
        conn: sqlite3.Connection,
        task_name: str,
        user_id: str,
        items: Iterable[tuple[str, str]],
        *,
        account: str | None = None,
        source: str = "runtime",
    ) -> int:
        rows = [
            (
                task_name,
                user_id,
                sign_date,
                signed_at,
                account,
                source,
            )
            for sign_date, signed_at in items
        ]
        if not rows:
            return 0
        conn.executemany(
            """
            INSERT INTO sign_records (
                task_name,
                user_id,
                sign_date,
                signed_at,
                account,
                source
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_name, user_id, sign_date) DO UPDATE SET
                signed_at = excluded.signed_at,
                account = excluded.account,
                source = excluded.source
            """,
            rows,
        )
        return len(rows)

    def upsert_record(
        self,
        task_name: str,
        user_id: str,
        sign_date: str,
        signed_at: str,
        *,
        account: str | None = None,
        source: str = "runtime",
    ) -> None:
        with self._connection() as conn:
            self._upsert_records(
                conn,
                task_name,
                user_id,
                [(sign_date, signed_at)],
                account=account,
                source=source,
            )
            conn.commit()

    def has_records(self, task_name: str, user_id: str) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM sign_records
                WHERE task_name = ? AND user_id = ?
                LIMIT 1
                """,
                (task_name, user_id),
            ).fetchone()
        return row is not None

    def load_records(self, task_name: str, user_id: str) -> dict[str, str]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT sign_date, signed_at
                FROM sign_records
                WHERE task_name = ? AND user_id = ?
                ORDER BY sign_date ASC
                """,
                (task_name, user_id),
            ).fetchall()
        return {row["sign_date"]: row["signed_at"] for row in rows}

    def list_record_groups(self) -> list[SignRecordGroup]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT task_name, user_id, sign_date, signed_at
                FROM sign_records
                ORDER BY task_name ASC, user_id ASC, sign_date DESC
                """
            ).fetchall()

        grouped: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for row in rows:
            key = (row["task_name"], row["user_id"])
            grouped.setdefault(key, []).append((row["sign_date"], row["signed_at"]))

        return [
            SignRecordGroup(task_name=task_name, user_id=user_id, records=records)
            for (task_name, user_id), records in grouped.items()
        ]

    def list_recent_records(
        self,
        limit: int = 10,
        *,
        task_name: str | None = None,
        user_id: str | None = None,
    ) -> list[RecentSignRecord]:
        query = [
            "SELECT task_name, user_id, sign_date, signed_at, account, source",
            "FROM sign_records",
        ]
        conditions = []
        params: list[object] = []
        if task_name:
            conditions.append("task_name = ?")
            params.append(task_name)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if conditions:
            query.append("WHERE " + " AND ".join(conditions))
        query.append("ORDER BY signed_at DESC, task_name ASC, user_id ASC")
        query.append("LIMIT ?")
        params.append(limit)

        with self._connection() as conn:
            rows = conn.execute("\n".join(query), params).fetchall()

        return [
            RecentSignRecord(
                task_name=row["task_name"],
                user_id=row["user_id"],
                sign_date=row["sign_date"],
                signed_at=row["signed_at"],
                account=row["account"],
                source=row["source"],
            )
            for row in rows
        ]

    @staticmethod
    def load_json_records(path: str | Path) -> dict[str, str]:
        file_path = Path(path)
        if not file_path.is_file():
            return {}
        try:
            with open(file_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def import_json_file(
        self,
        task_name: str,
        user_id: str,
        path: str | Path,
        *,
        account: str | None = None,
        source: str = "json_migrated",
    ) -> int:
        records = self.load_json_records(path)
        if not records:
            return 0
        with self._connection() as conn:
            count = self._upsert_records(
                conn,
                task_name,
                user_id,
                records.items(),
                account=account,
                source=source,
            )
            conn.commit()
        return count

    def migrate_all_json_records(
        self,
        *,
        legacy_user_id: str | None = None,
        remove_files: bool = False,
        account: str | None = None,
    ) -> MigrationSummary:
        summary = MigrationSummary()
        signs_dir = self.workdir / "signs"
        if not signs_dir.is_dir():
            return summary

        with self._connection() as conn:
            for path in sorted(signs_dir.rglob("sign_record.json")):
                resolved = self.resolve_record_target(
                    path, legacy_user_id=legacy_user_id
                )
                if resolved is None:
                    summary.skipped_files.append(path)
                    continue
                task_name, user_id = resolved
                count = self._upsert_records(
                    conn,
                    task_name,
                    user_id,
                    self.load_json_records(path).items(),
                    account=account,
                    source="json_migrated",
                )
                if count == 0:
                    continue
                summary.migrated_files += 1
                summary.migrated_records += count
                if remove_files:
                    path.unlink()
                    summary.removed_files += 1
            conn.commit()
        return summary

    def resolve_record_target(
        self,
        path: str | Path,
        *,
        legacy_user_id: str | None = None,
    ) -> tuple[str, str] | None:
        file_path = Path(path)
        signs_dir = self.workdir / "signs"
        relative_parts = file_path.relative_to(signs_dir).parts
        if len(relative_parts) >= 3:
            return relative_parts[0], relative_parts[1]
        if len(relative_parts) == 2:
            # Older layouts used signs/<task>/sign_record.json without a user_id
            # segment, so we need an explicit override or a single known user.
            user_id = legacy_user_id or self._infer_single_user_id()
            if user_id:
                return relative_parts[0], user_id
        return None

    def _infer_single_user_id(self) -> str | None:
        users_dir = self.workdir / "users"
        if not users_dir.is_dir():
            return None
        user_ids = sorted(path.name for path in users_dir.iterdir() if path.is_dir())
        if len(user_ids) == 1:
            return user_ids[0]
        return None
