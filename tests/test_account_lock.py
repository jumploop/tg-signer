"""账号级文件锁测试。

锁的核心契约:
- 同账号在同一 WebUI 进程内,第二次 start 被拒(锁被持有,即使前一进程已退出);
- 不同账号互不影响;
- 同进程 stop 后,锁被释放,下次 start 可获;
- start 异常路径(子进程早退、open 失败等)必须释放锁,不留泄漏;
- 跨进程模拟: 同进程模拟两个独立 lock 调用,验证第二个拿不到。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_RUNNER_PATH = Path(__file__).resolve().parents[1] / "tg_signer" / "webui" / "runner.py"
_spec = importlib.util.spec_from_file_location("tg_signer_webui_runner", _RUNNER_PATH)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


@pytest.fixture(autouse=True)
def _cleanup_state():
    """每个测试后清理 _PROCESSES / _LOCKS。

    ``terminate()`` 后必须 ``wait()`` 收割子进程,否则 Windows 上被强杀的
    子进程异步退出,会与下一个测试的 ``Popen``/``poll`` 产生时序竞态
    (flaky 的 "启动后立即退出" 误判为运行中)。
    """
    yield
    for key, proc in list(runner._PROCESSES.items()):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()
                proc.wait(timeout=5)
        runner._PROCESSES.pop(key, None)
        lock = runner._LOCKS.pop(key, None)
        if lock is not None:
            lock.release()


def test_account_lock_acquire_and_release(tmp_path):
    """同账号连续两次 acquire → 第二次抛 AccountLocked;release 后可重入。"""
    h1 = runner._acquire_account_lock(tmp_path, "alice")
    try:
        with pytest.raises(runner.AccountLocked):
            runner._acquire_account_lock(tmp_path, "alice")
        # 不同账号互不影响
        h2 = runner._acquire_account_lock(tmp_path, "bob")
        try:
            # 仍然: bob 占着锁时,alice 也能再次 acquire 吗? 不能,因为 alice 自己还拿着
            with pytest.raises(runner.AccountLocked):
                runner._acquire_account_lock(tmp_path, "alice")
        finally:
            h2.release()
    finally:
        h1.release()
    # 全部释放后 alice 可再次 acquire
    h3 = runner._acquire_account_lock(tmp_path, "alice")
    h3.release()


def test_account_lock_release_is_idempotent(tmp_path):
    """重复 release 不抛异常(LockHandle 内部置 _locked=False 防双 unlock)。"""
    h = runner._acquire_account_lock(tmp_path, "alice")
    h.release()
    h.release()  # 不应抛


def test_start_rejects_when_account_already_running(monkeypatch, tmp_path):
    """同 (kind, account) 第二次 start → 拒绝;stop 后可再次 start。"""
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )

    ok1, _ = runner.start("signer", "t1", tmp_path, "alice")
    assert ok1

    # 第二次 start 同账号(任意 task) → 拒绝
    ok2, msg2 = runner.start("signer", "t2", tmp_path, "alice")
    assert not ok2
    assert "alice" in msg2
    assert "已在运行" in msg2

    # stop 后可再 start
    ok_stop, _ = runner.stop("signer", "alice")
    assert ok_stop
    ok3, _ = runner.start("signer", "t3", tmp_path, "alice")
    assert ok3


def test_start_rejects_when_lock_held_by_orphan_handle(monkeypatch, tmp_path):
    """模拟「锁被持有但无活跃进程」的遗留状态 —— start 仍应被拒。"""
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )

    # 手动占一个锁(模拟另一个 WebUI 实例还在用)
    handle = runner._acquire_account_lock(tmp_path, "alice")
    try:
        ok, msg = runner.start("signer", "t1", tmp_path, "alice")
        assert not ok
        assert "alice" in msg
        # 不应在 _PROCESSES 中留条目
        assert "signer:alice" not in runner._PROCESSES
        assert "signer:alice" not in runner._LOCKS
    finally:
        handle.release()


def test_lock_released_after_immediate_exit(monkeypatch, tmp_path):
    """子进程早退路径必须释放锁,否则下次 start 永远拿不到。

    用 fake Popen 模拟「立即退出」与「正常运行」两种子进程,不依赖真实
    子进程的启动/退出耗时(本机 Python 因注入 shim 启动极慢,真实 `pass`
    子进程退出时间波动大,会与 grace 秒数竞态导致 flaky)。
    """
    state = {"running": False}

    class _FakeChild:
        pid = 4242

        def poll(self):
            return None if state["running"] else 1

        def wait(self, timeout=None):
            return 1

        def terminate(self):
            state["running"] = False

        def kill(self):
            state["running"] = False

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: _FakeChild())
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.0)

    ok, msg = runner.start("signer", "t_fail", tmp_path, "alice")
    assert ok is False
    assert "启动后立即退出" in msg
    assert "alice" not in runner._LOCKS

    # 锁已释放 → 下次可成功 start
    state["running"] = True
    ok2, _ = runner.start("signer", "t_ok", tmp_path, "alice")
    assert ok2, "上次早退后锁未释放,新进程被拒"


def test_lock_released_after_os_error(monkeypatch, tmp_path):
    """open 主日志失败 → 锁被释放(无任何残留)。"""
    log_path = tmp_path / "logs" / runner.DEFAULT_LOG_FILE_NAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.rmdir()
    log_path.parent.write_text("not a dir", encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )

    ok, msg = runner.start("signer", "t_handle_err", tmp_path, "alice")
    assert ok is False
    # 锁不残留
    assert "signer:alice" not in runner._LOCKS


def test_start_with_multiple_tasks_uses_single_lock(monkeypatch, tmp_path):
    """多任务 start 只占用一个账号锁(同进程多任务共享进程)。"""
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )

    ok, _ = runner.start("signer", ["t1", "t2", "t3"], tmp_path, "alice")
    assert ok
    # 只一个进程 + 一个锁
    assert len(runner._PROCESSES) == 1
    assert len(runner._LOCKS) == 1
    # 再次 start (任意 task) → 仍被拒
    ok2, _ = runner.start("signer", "t4", tmp_path, "alice")
    assert not ok2


def test_different_accounts_run_independently(monkeypatch, tmp_path):
    """不同账号互不干扰,可同时持有各自的锁。同账号不同 kind 也互斥。"""
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )

    ok1, _ = runner.start("signer", "t1", tmp_path, "alice")
    ok2, _ = runner.start("signer", "t1", tmp_path, "bob")
    ok3, _ = runner.start("signer", "t2", tmp_path, "charlie")
    assert ok1 and ok2 and ok3
    assert set(runner._LOCKS) == {"signer:alice", "signer:bob", "signer:charlie"}

    # 同账号下 signer 已在跑 → monitor 启动被拒(锁互斥)
    ok4, msg4 = runner.start("monitor", "m1", tmp_path, "alice")
    assert not ok4
    assert "alice" in msg4


def test_shutdown_all_releases_all_locks(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    runner.start("signer", "t1", tmp_path, "alice")
    runner.start("signer", "t1", tmp_path, "bob")
    assert len(runner._LOCKS) == 2

    runner.shutdown_all(timeout=3.0)
    assert runner._LOCKS == {}
