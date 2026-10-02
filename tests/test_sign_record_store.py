import json
import sqlite3
import threading
from pathlib import Path

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
# 迁移：先落库再删源文件
# ---------------------------------------------------------------------------


def _legacy_file(workdir, task, date="2026-03-17"):
    path = workdir / "signs" / task / "sign_record.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump({date: f"{date}T06:00:00+08:00"}, fp)
    return path


def test_migration_keeps_records_when_source_deletion_fails(tmp_path, monkeypatch):
    """源文件删不掉时，已写入的记录一条都不能丢。

    回归：``unlink()`` 原本排在循环里、``commit()`` 排在循环之后，而
    ``with conn`` 异常时回滚。删除失败（Windows 上被 WebUI/编辑器/杀软占用是
    家常便饭）一旦抛出异常，整个事务回滚 —— 而此前循环里已经删掉的文件找不回来，
    结果是**记录两边都不存在**。
    """
    workdir = tmp_path / ".signer"
    a = _legacy_file(workdir, "aaa")
    b = _legacy_file(workdir, "bbb", date="2026-03-18")
    store = SignRecordStore(workdir)

    def _always_fail(self, *args, **kwargs):
        raise OSError("另一个进程正占用该文件")

    monkeypatch.setattr(Path, "unlink", _always_fail)

    # 删除失败不得让整批迁移失败，更不得回滚已写入的记录。
    summary = store.migrate_all_json_records(legacy_user_id="123456", remove_files=True)

    assert summary.migrated_records == 2
    assert store.load_records("aaa", "123456") != {}, "aaa 的记录被回滚丢失"
    assert store.load_records("bbb", "123456") != {}, "bbb 的记录被回滚丢失"
    # 源文件仍在（没删成功就不该消失）
    assert a.is_file() and b.is_file()


def test_migration_reports_undeleted_files_instead_of_failing(tmp_path, monkeypatch):
    """JSON 删不掉时，记录已安全落库，应如实报告而不是整批失败。"""
    workdir = tmp_path / ".signer"
    a = _legacy_file(workdir, "aaa")
    store = SignRecordStore(workdir)

    def _always_fail(self, *args, **kwargs):
        raise OSError("文件正被占用")

    monkeypatch.setattr(Path, "unlink", _always_fail)

    summary = store.migrate_all_json_records(legacy_user_id="123456", remove_files=True)

    assert summary.migrated_records == 1
    assert summary.removed_files == 0
    assert [p for p, _reason in summary.undeleted_files] == [a]
    assert "占用" in summary.undeleted_files[0][1]
    # 记录确实落库了
    assert store.load_records("aaa", "123456") != {}


def test_migration_reports_unreadable_legacy_json_as_skipped(tmp_path):
    """损坏的 legacy JSON 必须进入 skipped_files，让 CLI 能打印告警。

    回归：``load_json_records`` 对坏文件返回 {}，原实现直接 continue，
    既不计入 skipped_files 也不删除，CLI 于是打印「迁移 0 条」而无任何提示。
    """
    workdir = tmp_path / ".signer"
    good = _legacy_file(workdir, "aaa")
    bad = workdir / "signs" / "bbb" / "sign_record.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text('{"2026-03-17": "trunc', encoding="utf-8")

    store = SignRecordStore(workdir)
    summary = store.migrate_all_json_records(legacy_user_id="123456", remove_files=True)

    assert summary.migrated_records == 1
    assert good not in summary.skipped_files
    assert summary.skipped_files == [bad], "损坏文件未被报告为跳过"
    # 损坏的文件绝不能被删除 —— 那是用户唯一的手工备份
    assert bad.is_file()


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


# ---------------------------------------------------------------------------
# 连接生命周期:必须显式关闭,不能等 gc 兜底
# ---------------------------------------------------------------------------


def _track_connections(monkeypatch) -> list[sqlite3.Connection]:
    """记录 `_connect()` 实际交付给调用方的连接,事后可检查其是否已关闭。"""
    opened: list[sqlite3.Connection] = []
    original = SignRecordStore._connect

    def tracking_connect(self):
        conn = original(self)
        opened.append(conn)
        return conn

    monkeypatch.setattr(SignRecordStore, "_connect", tracking_connect)
    return opened


def _assert_all_closed(connections: list[sqlite3.Connection]) -> None:
    # sqlite3.Connection 没有 `closed` 属性,关闭后执行 SQL 抛
    # ProgrammingError 是唯一可靠的探针。
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_public_methods_close_their_connections(tmp_path, monkeypatch):
    """每个公开方法用完都要关闭连接。

    判别性:`with self._connect() as conn` 只提交/回滚事务、**不关闭连接**,
    旧实现下这些连接此刻仍可执行 SQL,`_assert_all_closed` 会整体失败。
    8 个线程 x 200 轮时,漏关会让进程同时压着大量库与 WAL/-shm 句柄。
    """
    store = SignRecordStore(tmp_path / ".signer")
    opened = _track_connections(monkeypatch)

    store.upsert_record("t", "u", "2026-09-01", "2026-09-01T06:00:00+08:00")
    store.has_records("t", "u")
    store.load_records("t", "u")
    store.list_record_groups()
    store.list_recent_records(limit=5)

    assert len(opened) == 5
    _assert_all_closed(opened)


def test_migration_paths_close_their_connections(tmp_path, monkeypatch):
    """带显式 commit 的迁移路径同样要关闭连接。"""
    workdir = tmp_path / ".signer"
    record_file = workdir / "signs" / "linuxdo" / "sign_record.json"
    record_file.parent.mkdir(parents=True, exist_ok=True)
    record_file.write_text(
        json.dumps({"2026-03-17": "2026-03-17T06:00:00+08:00"}), encoding="utf-8"
    )

    store = SignRecordStore(workdir)
    opened = _track_connections(monkeypatch)

    assert store.import_json_file("linuxdo", "123456", record_file) == 1
    # 同一份数据再迁一次：ON CONFLICT 上的「只有更新的记录才覆盖」使这次
    # 一行都不会被改写，所以诚实地报告 0，而不是照抄提交给 executemany 的行数。
    assert store.migrate_all_json_records(legacy_user_id="123456").migrated_records == 0

    assert len(opened) == 2
    _assert_all_closed(opened)
    # 数据本身不受影响（放在连接计数断言之后，避免多开一个连接）
    assert store.load_records("linuxdo", "123456") == {
        "2026-03-17": "2026-03-17T06:00:00+08:00"
    }


def test_migration_does_not_overwrite_newer_runtime_record(tmp_path):
    """legacy JSON 不得压过运行期写入的记录。

    回归：ON CONFLICT 曾是无条件 DO UPDATE，跑一遍 `migrate-sign-records`
    就把重叠的那些天改写成 JSON 里的旧时间戳、account 抹成 NULL、
    source 从 runtime 翻成 json_migrated —— 多账号归属和精确时刻都没了。
    """
    workdir = tmp_path / ".signer"
    record_file = workdir / "signs" / "linuxdo" / "sign_record.json"
    record_file.parent.mkdir(parents=True, exist_ok=True)
    record_file.write_text(
        json.dumps({"2026-03-17": "2026-03-17T06:00:00+08:00"}), encoding="utf-8"
    )

    store = SignRecordStore(workdir)
    store.upsert_record(
        "linuxdo",
        "123456",
        "2026-03-17",
        "2026-03-17T06:00:31.482913+08:00",
        account="acct_b",
        source="runtime",
    )

    store.migrate_all_json_records(legacy_user_id="123456")

    rows = store.load_records("linuxdo", "123456")
    assert rows["2026-03-17"] == "2026-03-17T06:00:31.482913+08:00", (
        "较新的运行期记录被旧的 legacy JSON 覆盖了"
    )
    latest = store.list_recent_records(limit=10)
    assert latest[0].account == "acct_b", "account 归属被迁移抹成了 NULL"
    assert latest[0].source == "runtime", "source 被改成了 json_migrated"


def test_connection_is_closed_even_when_the_body_raises(tmp_path, monkeypatch):
    """方法体抛异常时连接也要关闭(finally 语义),否则失败路径会漏句柄。

    判别性:只在正常出口关闭的实现会在这里留下未关闭的连接。
    """
    store = SignRecordStore(tmp_path / ".signer")
    opened = _track_connections(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(SignRecordStore, "_upsert_records", boom)

    with pytest.raises(RuntimeError, match="boom"):
        store.upsert_record("t", "u", "2026-09-01", "2026-09-01T06:00:00+08:00")

    assert len(opened) == 1
    _assert_all_closed(opened)
