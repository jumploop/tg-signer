import importlib.util
import sys
import time
from pathlib import Path

import pytest

_RUNNER_PATH = Path(__file__).resolve().parents[1] / "tg_signer" / "webui" / "runner.py"
_spec = importlib.util.spec_from_file_location("tg_signer_webui_runner", _RUNNER_PATH)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


@pytest.fixture(autouse=True)
def _cleanup_processes():
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


def test_default_log_file_name_is_unified():
    # 主日志文件名固定,所有日志聚合到同一个文件
    assert runner.DEFAULT_LOG_FILE_NAME == "tg-signer.log"


def test_process_key_is_per_account():
    # 0.9.12 起 key 是 (kind, account),同账号多任务共享一个进程
    assert runner.process_key("signer", "mingtian") == "signer:mingtian"
    assert runner.process_key("monitor", "mingtian") == "monitor:mingtian"


def test_build_command_signer_single_task(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner, "sys", type("FakeSys", (), {"executable": "/usr/bin/python"})
    )
    cmd = runner.build_command("signer", "my_sign", tmp_path, "acc1")
    assert cmd[0] == "/usr/bin/python"
    assert cmd[1:4] == ["-m", "tg_signer", "--workdir"]
    assert "--account" in cmd
    assert "--session_dir" in cmd
    assert "--log-dir" in cmd
    # 不再为每个任务单独传 --log-file,统一到主日志
    assert "--log-file" not in cmd
    assert cmd[-2:] == ["run", "my_sign"]


def test_build_command_signer_multiple_tasks(monkeypatch, tmp_path):
    """多任务被拼接到同一 CLI 命令末尾,共享一个子进程。"""
    monkeypatch.setattr(runner, "sys", type("FakeSys", (), {"executable": "py"}))
    cmd = runner.build_command("signer", ["t1", "t2", "t3"], tmp_path, "acc")
    assert cmd[-4:] == ["run", "t1", "t2", "t3"]


def test_build_command_kinds_proxy_and_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "sys", type("FakeSys", (), {"executable": "py"}))
    # 单任务: 仍可接受 str,自动包成 list
    assert runner.build_command("monitor", "m1", tmp_path, "a")[-3:] == [
        "monitor",
        "run",
        "m1",
    ]
    assert runner.build_command("automation", "a1", tmp_path, "a")[-3:] == [
        "automation",
        "run",
        "a1",
    ]
    # 多任务: 三个 kind 都要正确拼接
    assert runner.build_command("signer", ["s1", "s2"], tmp_path, "a")[-3:] == [
        "run",
        "s1",
        "s2",
    ]
    assert runner.build_command("monitor", ["m1", "m2"], tmp_path, "a")[-4:] == [
        "monitor",
        "run",
        "m1",
        "m2",
    ]
    assert runner.build_command("automation", ["a1", "a2"], tmp_path, "a")[-4:] == [
        "automation",
        "run",
        "a1",
        "a2",
    ]
    # proxy 仍正常拼接
    cmd = runner.build_command("signer", "s1", tmp_path, "a", proxy="socks5://x:1")
    assert cmd[cmd.index("--proxy") :] == ["--proxy", "socks5://x:1", "run", "s1"]
    with pytest.raises(ValueError):
        runner.build_command("unknown", "t", tmp_path, "a")
    # 空任务列表报错
    with pytest.raises(ValueError):
        runner.build_command("signer", [], tmp_path, "a")


def test_start_then_stop(monkeypatch, tmp_path):
    """单任务: start 拉起进程, stop 终止。key 是 (kind, account)。"""
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    ok, msg = runner.start("signer", "t1", tmp_path, "acc")
    assert ok, msg
    key = runner.process_key("signer", "acc")
    assert runner.running_tasks().get(key) is True
    # account 在 kind 下唯一: 重复 start 同 account 同 kind → 拒绝
    ok_dup, msg_dup = runner.start("signer", "t1", tmp_path, "acc")
    assert not ok_dup
    assert "已在运行" in msg_dup
    assert "acc" in msg_dup

    ok_stop, _msg = runner.stop("signer", "acc")
    assert ok_stop
    assert runner.running_tasks().get(key) is not True
    ok_stop_again, _msg = runner.stop("signer", "acc")
    assert not ok_stop_again


def test_start_accepts_list_of_tasks(monkeypatch, tmp_path):
    """start 接受 List[str],所有任务拼接到一条 CLI 命令。"""
    captured_cmds: list = []

    def fake_build(kind, tasks, workdir, account, proxy=None):
        cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
        captured_cmds.append(
            (kind, list(tasks) if not isinstance(tasks, str) else [tasks])
        )
        return cmd

    monkeypatch.setattr(runner, "build_command", fake_build)
    ok, msg = runner.start("signer", ["a", "b", "c"], tmp_path, "acc")
    assert ok, msg
    assert captured_cmds == [("signer", ["a", "b", "c"])]
    runner.stop("signer", "acc")


def test_running_tasks_cleans_finished(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "pass"],
    )
    runner.start("signer", "t2", tmp_path, "acc")
    deadline = time.time() + 10
    while runner.running_tasks().get("signer:acc", True) and time.time() < deadline:
        time.sleep(0.05)
    assert "signer:acc" not in runner.running_tasks()


def test_status_tracks_process_lifecycle(monkeypatch, tmp_path):
    assert runner.status("signer", "t3") is False

    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    runner.start("signer", "t3", tmp_path, "acc")
    assert runner.status("signer", "acc") is True

    ok, _msg = runner.stop("signer", "acc")
    assert ok
    assert runner.status("signer", "acc") is False

    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "pass"],
    )
    runner.start("signer", "t4", tmp_path, "acc")
    deadline = time.time() + 10
    while runner.status("signer", "acc") and time.time() < deadline:
        time.sleep(0.05)
    assert runner.status("signer", "acc") is False


def test_start_detects_immediate_exit(monkeypatch, tmp_path):
    # 子进程启动后立即以 exit code 1 退出 → 启动失败
    # 用 fake Popen 模拟,不依赖真实子进程启动耗时(本机 Python 注入 shim
    # 启动极慢,真实 `pass` 子进程退出时间波动大,会与 grace 秒数竞态)。
    class _FakeChild:
        pid = 4242

        def poll(self):
            return 1  # 已退出

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: _FakeChild())
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.0)

    ok, msg = runner.start("signer", "t_fail", tmp_path, "acc")
    assert ok is False
    assert "启动后立即退出" in msg
    # 不应留在 _PROCESSES / _LOCKS 里
    assert "signer:acc" not in runner._PROCESSES
    assert "signer:acc" not in runner._LOCKS


def test_shutdown_all_terminates_tracked_processes(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    # 不同 account 各自一个进程;不同 (kind, account) 进程独立
    # (同 account 即使不同 kind 也应被账户锁拒绝 —— 已在 test_account_lock_is_per_account 测)
    runner.start("signer", "t1", tmp_path, "acc1")
    runner.start("signer", "t2", tmp_path, "acc2")
    runner.start("monitor", "m1", tmp_path, "acc3")
    assert len(runner._PROCESSES) == 3

    stopped = runner.shutdown_all(timeout=3.0)
    assert set(stopped) == {"signer:acc1", "signer:acc2", "monitor:acc3"}
    assert runner._PROCESSES == {}
    assert runner._LOCKS == {}
    assert runner.running_tasks() == {}


def test_shutdown_all_no_op_when_empty():
    assert runner.shutdown_all() == []


def test_start_redirects_stdout_stderr_to_main_log(monkeypatch, tmp_path):
    """子进程 stdout/stderr 应被重定向到 <workdir>/logs/<main_log>,而非 DEVNULL。"""
    main_log = tmp_path / "logs" / runner.DEFAULT_LOG_FILE_NAME
    marker = "RUNNER_REDIRECT_MARKER_42"
    # grace 调到 0.3s:子进程先 flush marker 再 sleep 60,grace 期内仍存活
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.3)
    # 子进程脚本:先 flush marker,再长睡,避免被 grace 早退检测捕获
    child_script = (
        "import sys, time; "
        "sys.stdout.write('" + marker + "' + chr(10)); "
        "sys.stdout.flush(); time.sleep(60)"
    )
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", child_script],
    )
    ok, msg = runner.start("signer", "t_redir", tmp_path, "acc")
    assert ok, msg
    try:
        # 等 marker 真正落盘(子进程 flush 后写到 main_log,文件 I/O 略有延迟)
        deadline = time.time() + 10
        while time.time() < deadline:
            if main_log.is_file() and marker in main_log.read_text(
                encoding="utf-8", errors="ignore"
            ):
                break
            time.sleep(0.05)
    finally:
        runner.stop("signer", "acc")

    # 主日志文件应存在并包含 marker
    assert main_log.is_file(), f"expected main log at {main_log}"
    content = main_log.read_text(encoding="utf-8", errors="ignore")
    assert marker in content, (
        f"stdout was not redirected to main log; content was:\n{content!r}"
    )


def test_start_creates_log_dir(tmp_path):
    """start() 启动前应自动创建 <workdir>/logs 目录。"""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    assert not (workdir / "logs").exists()
    # 用一个会立即退出的子进程(避免与时间竞争)
    import sys as _sys

    import tg_signer.webui.runner as _runner

    orig_build = _runner.build_command
    _runner.build_command = lambda *a, **k: [_sys.executable, "-c", "pass"]
    try:
        _runner.start("signer", "t_mkdir", workdir, "acc")
    finally:
        _runner.build_command = orig_build
    assert (workdir / "logs").is_dir()
    assert (workdir / "logs" / runner.DEFAULT_LOG_FILE_NAME).is_file()


def test_start_propagates_file_handle_error(monkeypatch, tmp_path):
    """若打开主日志失败,start() 应返回失败而非静默丢日志。"""
    log_path = tmp_path / "logs" / runner.DEFAULT_LOG_FILE_NAME
    # 让目录创建后,open() 失败:把 logs/ 弄成文件
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.rmdir()
    log_path.parent.write_text("not a dir", encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    ok, msg = runner.start("signer", "t_handle_err", tmp_path, "acc")
    assert ok is False
    assert "启动失败" in msg
    # 启动失败 → 不留任何痕迹(包括 lock)
    assert "signer:acc" not in runner._PROCESSES
    assert "signer:acc" not in runner._LOCKS


def test_start_closes_log_fp_after_popen(monkeypatch, tmp_path):
    """start() 在 Popen 之后应立即关闭父进程的日志文件对象,避免 fd 泄漏。"""
    captured = {}

    class _FakeChild:
        pid = 12345

        def poll(self):
            return None  # 子进程仍在运行(成功路径)

        def wait(self, timeout=None):
            return 0

    def fake_popen(cmd, stdout=None, stderr=None):
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        return _FakeChild()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.0)

    ok, msg = runner.start("signer", "t_fd", tmp_path, "acc")
    assert ok, msg
    # 传给子进程的就是那个日志文件对象,父进程必须在 Popen 后关闭它
    assert captured["stdout"] is not None
    assert captured["stdout"] is captured["stderr"]
    assert captured["stdout"].closed, "父进程日志文件对象未在 Popen 后关闭(fd 泄漏)"
    runner._PROCESSES.pop("signer:acc", None)
    lock = runner._LOCKS.pop("signer:acc", None)
    if lock is not None:
        lock.release()


def test_start_reaps_child_on_early_exit(monkeypatch, tmp_path):
    """启动后立即退出的子进程应被 wait() 收割,避免 POSIX 僵尸进程。"""
    waited = {"called": False}

    class _FakeChild:
        def poll(self):
            return 1  # 已退出,exit code 1

        def wait(self, timeout=None):
            waited["called"] = True
            return 1

    def fake_popen(cmd, stdout=None, stderr=None):
        return _FakeChild()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.0)

    ok, msg = runner.start("signer", "t_zombie", tmp_path, "acc")
    assert ok is False
    assert "启动后立即退出" in msg
    assert waited["called"], "早退子进程未被 wait() 收割"
    # 不应留在 _PROCESSES / _LOCKS 里
    assert "signer:acc" not in runner._PROCESSES
    assert "signer:acc" not in runner._LOCKS
