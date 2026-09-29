import json
import sqlite3
import threading

import pytest

from tg_signer.sign_record_store import SignRecordStore


def test_sign_record_store_upsert_and_list_groups(tmp_path):
    workdir = tmp_path / ".signer"
    store = SignRecordStore(workdir)

    store.upsert_record(
        "linuxdo",
        "123456",
        "2026-03-17",
        "2026-03-17T06:00:00+08:00",
        account="acct",
    )
    store.upsert_record(
        "linuxdo",
        "123456",
        "2026-03-18",
        "2026-03-18T06:00:00+08:00",
        account="acct",
    )

    assert store.db_path.is_file()
    assert store.load_records("linuxdo", "123456") == {
        "2026-03-17": "2026-03-17T06:00:00+08:00",
        "2026-03-18": "2026-03-18T06:00:00+08:00",
    }

    groups = store.list_record_groups()
    assert len(groups) == 1
    assert groups[0].task_name == "linuxdo"
    assert groups[0].user_id == "123456"
    assert groups[0].records == [
        ("2026-03-18", "2026-03-18T06:00:00+08:00"),
        ("2026-03-17", "2026-03-17T06:00:00+08:00"),
    ]


def test_sign_record_store_runs_explicit_schema_migrations(tmp_path):
    workdir = tmp_path / ".signer"
    workdir.mkdir(parents=True, exist_ok=True)
    db_path = workdir / "data.sqlite3"

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA user_version = 0")
        conn.commit()

    store = SignRecordStore(workdir)
    store.upsert_record(
        "linuxdo",
        "123456",
        "2026-03-17",
        "2026-03-17T06:00:00+08:00",
    )

    with sqlite3.connect(db_path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        count = conn.execute("SELECT COUNT(*) FROM sign_records").fetchone()[0]

    assert version == store.SCHEMA_VERSION
    assert count == 1


def test_sign_record_store_lists_recent_records_with_filters(tmp_path):
    workdir = tmp_path / ".signer"
    store = SignRecordStore(workdir)
    store.upsert_record(
        "linuxdo",
        "1001",
        "2026-03-17",
        "2026-03-17T06:00:00+08:00",
    )
    store.upsert_record(
        "linuxdo",
        "1001",
        "2026-03-18",
        "2026-03-18T06:00:00+08:00",
    )
    store.upsert_record(
        "v2ex",
        "2002",
        "2026-03-16",
        "2026-03-16T06:00:00+08:00",
    )

    recent = store.list_recent_records(limit=2)
    assert [(record.task_name, record.sign_date) for record in recent] == [
        ("linuxdo", "2026-03-18"),
        ("linuxdo", "2026-03-17"),
    ]

    filtered = store.list_recent_records(limit=10, task_name="v2ex", user_id="2002")
    assert [
        (record.task_name, record.user_id, record.sign_date) for record in filtered
    ] == [("v2ex", "2002", "2026-03-16")]


def test_sign_record_store_migrates_legacy_json_with_explicit_user_id(tmp_path):
    workdir = tmp_path / ".signer"
    record_file = workdir / "signs" / "linuxdo" / "sign_record.json"
    record_file.parent.mkdir(parents=True, exist_ok=True)
    with open(record_file, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "2026-03-17": "2026-03-17T06:00:00+08:00",
                "2026-03-18": "2026-03-18T06:00:00+08:00",
            },
            fp,
        )

    store = SignRecordStore(workdir)
    summary = store.migrate_all_json_records(legacy_user_id="123456")

    assert summary.migrated_files == 1
    assert summary.migrated_records == 2
    assert summary.skipped_files == []
    assert store.load_records("linuxdo", "123456") == {
        "2026-03-17": "2026-03-17T06:00:00+08:00",
        "2026-03-18": "2026-03-18T06:00:00+08:00",
    }


def test_sign_record_store_skips_ambiguous_legacy_json(tmp_path):
    workdir = tmp_path / ".signer"
    (workdir / "users" / "1001").mkdir(parents=True, exist_ok=True)
    (workdir / "users" / "1002").mkdir(parents=True, exist_ok=True)
    record_file = workdir / "signs" / "linuxdo" / "sign_record.json"
    record_file.parent.mkdir(parents=True, exist_ok=True)
    with open(record_file, "w", encoding="utf-8") as fp:
        json.dump({"2026-03-17": "2026-03-17T06:00:00+08:00"}, fp)

    store = SignRecordStore(workdir)
    summary = store.migrate_all_json_records()

    assert summary.migrated_files == 0
    assert summary.migrated_records == 0
    assert summary.skipped_files == [record_file]


# ---------------------------------------------------------------------------
# 并发写:WebUI 进程与多个任务子进程会同时写同一份 data.sqlite3
# ---------------------------------------------------------------------------


# 8 x 200 是这个缺陷的复现强度:轮次太低(如 30)时旧实现也能侥幸通过,
# 测试就失去判别力。代价是两条用例合计约 20s,属于有意承担的回归成本。
_CONCURRENT_WRITERS = 8
_CONCURRENT_ROUNDS = 200


def _run_concurrent_upserts(workdir, writers: int, rounds: int, warmup: bool):
    """并发写 workdir 下的 data.sqlite3,返回每个写者捕获到的异常。"""
    if warmup:
        SignRecordStore(workdir).upsert_record("warmup", "u", "2026-01-01", "t")

    errors: list[str] = []
    start = threading.Barrier(writers)

    def worker(index: int) -> None:
        store = SignRecordStore(workdir)
        start.wait()
        try:
            for round_index in range(rounds):
                store.upsert_record(
                    f"task{round_index % 5}",
                    f"user{index}",
                    f"2026-09-{round_index % 28 + 1:02d}",
                    "2026-09-29T06:00:00+08:00",
                    account=f"acc{index}",
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


@pytest.mark.parametrize("warmup", [False, True], ids=["cold", "initialized"])
def test_concurrent_upserts_never_raise_database_is_locked(tmp_path, warmup):
    """并发写不得抛 `database is locked`。

    冷启动的场景尤其重要:多个进程同时从 delete 切向 WAL 时,SQLite 对失败者
    直接返回 SQLITE_BUSY 而不进 busy handler。历史上这里 8 线程有 5~6 个失败,
    且 sqlite3.Error 不是 OSError,会一路逃逸出 normal_run 打死整个签到任务。
    """
    errors = _run_concurrent_upserts(
        tmp_path / ".signer",
        writers=_CONCURRENT_WRITERS,
        rounds=_CONCURRENT_ROUNDS,
        warmup=warmup,
    )
    assert errors == []


def test_connect_enables_wal_and_busy_timeout(tmp_path):
    store = SignRecordStore(tmp_path / ".signer")
    with store._connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] > 0


def test_wal_switch_failure_is_tolerated(monkeypatch):
    """并发切换 WAL 时 SQLITE_BUSY 必须被吞掉,不能中断连接。"""

    class FakeConn:
        def execute(self, sql):
            if "journal_mode" in sql:
                raise sqlite3.OperationalError("database is locked")

    SignRecordStore._enable_wal(FakeConn())
