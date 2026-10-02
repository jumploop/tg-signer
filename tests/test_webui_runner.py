import importlib.util
import sys
import threading
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
                # kill() 之后仍 wait 不到也不能让 teardown 抛出去：
                # 那会以「另一个测试失败」的形式掩盖真正的错误。
                try:
                    proc.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    pass
        runner._PROCESSES.pop(key, None)
        runner._TASK_NAMES.pop(key, None)
        lock = runner._LOCKS.pop(key, None)
        if lock is not None:
            lock.release()


def test_default_log_file_name_is_unified():
    # 主日志文件名固定,所有日志聚合到同一个文件
    assert runner.DEFAULT_LOG_FILE_NAME == "tg-signer.log"


def test_stop_releases_the_account_lock_when_kill_does_not_reap(tmp_path):
    """kill() 之后仍 wait 不到时不得抛裸 TimeoutExpired，必须释放锁。

    回归：旧实现直接 ``proc.wait(timeout=5)``，异常一路冒到 HTTP 层 →
    500 + traceback，而账号锁和注册表项都留在原地，该账号被永久占住。
    """
    import subprocess

    key = runner.process_key("signer", "acc", tmp_path)
    handle = runner._acquire_account_lock(tmp_path, "acc")
    runner._LOCKS[key] = handle

    class Stubborn:
        """terminate/kill 都无效，wait 永远超时。"""

        pid = 4242

        def poll(self):
            return None

        def terminate(self):
            pass

        def kill(self):
            pass

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("stubborn", timeout or 0)

    runner._PROCESSES[key] = Stubborn()
    runner._TASK_NAMES[key] = ["t"]

    ok, message = runner.stop("signer", "acc", tmp_path)

    assert ok is True
    assert "未能确认退出" in message
    # 关键：注册表项与账号锁都已清理，账号可以重新启动。
    assert key not in runner._PROCESSES
    assert key not in runner._TASK_NAMES
    assert key not in runner._LOCKS


def test_process_key_is_per_account():
    # 展示键不含 workdir（UI 上展示用）
    assert runner.process_key("signer", "mingtian") == "signer:mingtian"


def test_process_key_is_scoped_by_workdir(tmp_path):
    # 不同 workdir 是彼此独立的账号命名空间，注册表键必须带上 workdir，
    # 否则 WebUI 切目录后新目录里的同名账号会被旧目录的进程挡住。
    a = runner.process_key("signer", "acc", tmp_path / "a")
    b = runner.process_key("signer", "acc", tmp_path / "b")
    assert a != b
    assert a.endswith("signer:acc") and b.endswith("signer:acc")
    # 同一 workdir 下同名账号仍然共享一个进程
    assert runner.process_key("signer", "acc", tmp_path / "a") == a
    # 展示层仍然是不带 workdir 的稳定标识
    assert runner.display_key("signer", "acc") == "signer:acc"


def test_build_command_signer_single_task(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner, "sys", type("FakeSys", (), {"executable": "/usr/bin/python"})
    )
    cmd = runner.build_command("signer", "my_sign", tmp_path, "acc1")
    assert cmd[0] == "/usr/bin/python"
    assert cmd[1:4] == ["-m", "tg_signer", "--workdir"]
    assert "--account" in cmd
    assert "--session_dir" in cmd
    # 子进程日志按 (kind, account) 隔离:不隔离的话 CLI 的 --log-file 默认值是
    # 相对路径 logs/tg-signer.log,子进程会在自己 cwd 下另建一份 logs/,而
    # warn.log / error.log 又被所有子进程共享、并发轮转互相截断。
    child_log_dir = tmp_path / "logs" / "signer-acc1"
    assert cmd[cmd.index("--log-dir") + 1] == str(child_log_dir)
    assert cmd[cmd.index("--log-file") + 1] == str(child_log_dir / "tg-signer.log")
    assert cmd[-2:] == ["run", "my_sign"]


def test_build_command_signer_multiple_tasks(monkeypatch, tmp_path):
    """多任务被拼接到同一 CLI 命令末尾,共享一个子进程。"""
    monkeypatch.setattr(runner, "sys", type("FakeSys", (), {"executable": "py"}))
    cmd = runner.build_command("signer", ["t1", "t2", "t3"], tmp_path, "acc")
    assert cmd[-4:] == ["run", "t1", "t2", "t3"]


def test_build_command_kinds_proxy_and_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "sys", type("FakeSys", (), {"executable": "py"}))
    # 单任务: 仍可接受 str,自动包成 list
    assert runner.build_command("automation", "a1", tmp_path, "a")[-3:] == [
        "automation",
        "run",
        "a1",
    ]
    # 多任务: signer / automation 都要正确拼接
    assert runner.build_command("signer", ["s1", "s2"], tmp_path, "a")[-3:] == [
        "run",
        "s1",
        "s2",
    ]
    assert runner.build_command("automation", ["a1", "a2"], tmp_path, "a")[-4:] == [
        "automation",
        "run",
        "a1",
        "a2",
    ]
    # 代理凭据不进 argv:同机可以用 ps / 任务管理器读到 --proxy 的明文密码,
    # 所以改由 TG_PROXY 环境变量传给子进程(CLI 的 --proxy 声明了 envvar)。
    cmd = runner.build_command("signer", "s1", tmp_path, "a")
    assert "--proxy" not in cmd
    assert not any("socks5://" in part for part in cmd)
    monkeypatch.delenv("TG_PROXY", raising=False)
    assert "TG_PROXY" not in runner.build_env(None)
    assert runner.build_env("socks5://user:pass@127.0.0.1:1080")["TG_PROXY"] == (
        "socks5://user:pass@127.0.0.1:1080"
    )
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
    # 展示键仍然是不带 workdir 的 "kind:account"
    assert runner.running_tasks().get("signer:acc") is True
    # account 在 kind 下唯一: 重复 start 同 account 同 kind → 拒绝
    ok_dup, msg_dup = runner.start("signer", "t1", tmp_path, "acc")
    assert not ok_dup
    assert "已在运行" in msg_dup
    assert "acc" in msg_dup

    ok_stop, _msg = runner.stop("signer", "acc", tmp_path)
    assert ok_stop
    assert runner.running_tasks().get("signer:acc") is not True
    ok_stop_again, _msg = runner.stop("signer", "acc", tmp_path)
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
    runner.stop("signer", "acc", tmp_path)


def test_running_task_names_records_started_tasks(monkeypatch, tmp_path):
    """start 后 running_task_names 返回该进程实际运行的任务名列表。"""
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    ok, msg = runner.start("signer", ["daily", "nightly"], tmp_path, "acc")
    assert ok, msg
    assert runner.running_task_names() == {"signer:acc": ["daily", "nightly"]}
    runner.stop("signer", "acc", tmp_path)


def test_running_task_names_cleared_after_stop(monkeypatch, tmp_path):
    """stop 后任务名应被清理,避免下次同 key 启动显示旧任务。"""
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    ok, _msg = runner.start("signer", ["old_task"], tmp_path, "acc")
    assert ok
    runner.stop("signer", "acc", tmp_path)
    assert "signer:acc" not in runner.running_task_names()


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


def _wait_for_status(kind, account, workdir, want, timeout=15.0):
    """轮询 status 直到达到期望值，避免用「睡 X 秒后应该成立」的方式断言。

    这类断言在本机满负载跑全量套件时会偶发失败（子进程何时真正进入 sleep、
    terminate 何时被回收都受调度影响），而与被测逻辑无关。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if runner.status(kind, account, workdir) is want:
            return True
        time.sleep(0.05)
    return False


def test_status_tracks_process_lifecycle(monkeypatch, tmp_path):
    assert runner.status("signer", "t3", tmp_path) is False

    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    ok, _ = runner.start("signer", "t3", tmp_path, "acc")
    assert ok, "常驻进程应启动成功"
    assert _wait_for_status("signer", "acc", tmp_path, True)

    ok, _msg = runner.stop("signer", "acc", tmp_path)
    assert ok
    assert _wait_for_status("signer", "acc", tmp_path, False)

    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "pass"],
    )
    runner.start("signer", "t4", tmp_path, "acc")
    assert _wait_for_status("signer", "acc", tmp_path, False)


def test_same_account_in_two_workdirs_does_not_collide(monkeypatch, tmp_path):
    """切 workdir 后同名账号必须能独立启动（回归：键里缺 workdir 的老 bug）。"""
    workdir_a = tmp_path / "a"
    workdir_b = tmp_path / "b"
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    try:
        ok_a, msg_a = runner.start("signer", "daily", workdir_a, "acc")
        assert ok_a, msg_a
        # 老实现的键是 "signer:acc"（不含 workdir），B 会直接撞上 A 的进程
        ok_b, msg_b = runner.start("signer", "daily", workdir_b, "acc")
        assert ok_b, f"切换 workdir 后同名账号被旧目录的进程挡住: {msg_b}"
        # 两个 workdir 的账号锁必须落在各自的目录里
        assert (workdir_a / "acc.lock").exists()
        assert (workdir_b / "acc.lock").exists()
    finally:
        runner.stop("signer", "acc", workdir_a)
        runner.stop("signer", "acc", workdir_b)


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
    assert runner.process_key("signer", "acc", tmp_path) not in runner._PROCESSES
    assert runner.process_key("signer", "acc", tmp_path) not in runner._LOCKS


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
    runner.start("automation", "a1", tmp_path, "acc3")
    assert len(runner._PROCESSES) == 3

    stopped = runner.shutdown_all(timeout=3.0)
    assert set(stopped) == {"signer:acc1", "signer:acc2", "automation:acc3"}
    assert runner._PROCESSES == {}
    assert runner._LOCKS == {}
    assert runner.running_tasks() == {}


def test_shutdown_all_no_op_when_empty():
    assert runner.shutdown_all() == []


def test_start_redirects_stdout_stderr_to_child_dir_not_main_log(monkeypatch, tmp_path):
    """子进程 stdout/stderr 落到子目录,且**不**写顶层主日志。

    顶层主日志由主进程的 RotatingFileHandler 独占;子进程若也往里写,它继承来的
    裸 fd 在轮转后会指向被改名的旧 inode,输出从此静默消失。
    """
    main_log = tmp_path / "logs" / runner.DEFAULT_LOG_FILE_NAME
    stdout_log = runner.child_stdout_log(tmp_path, "signer", "acc")
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
            if stdout_log.is_file() and marker in stdout_log.read_text(
                encoding="utf-8", errors="ignore"
            ):
                break
            time.sleep(0.05)
    finally:
        runner.stop("signer", "acc", tmp_path)

    # 子目录文件应存在并包含 marker
    assert stdout_log.is_file(), f"expected stdout log at {stdout_log}"
    content = stdout_log.read_text(encoding="utf-8", errors="ignore")
    assert marker in content, (
        f"stdout was not redirected to child dir; content was:\n{content!r}"
    )
    # 关键断言:顶层主日志不得被子进程写入(轮转后会写进旧 inode)。
    assert not main_log.exists() or marker not in main_log.read_text(
        encoding="utf-8", errors="ignore"
    ), "子进程 stdout 泄漏进了顶层主日志"


def test_start_creates_log_dir(tmp_path):
    """start() 启动前应自动创建 <workdir>/logs 及其子目录下的 stdout 日志。

    顶层 tg-signer.log 不再由 start() 创建 —— 它归主进程的 RotatingFileHandler
    独占，由 _setup_webui_logger 在服务启动时负责。
    """
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
    assert runner.child_stdout_log(workdir, "signer", "acc").is_file()
    assert not (workdir / "logs" / runner.DEFAULT_LOG_FILE_NAME).exists()


def test_start_propagates_file_handle_error(monkeypatch, tmp_path):
    """若打开子进程 stdout 日志失败,start() 应返回失败而非静默丢日志。"""
    log_path = runner.child_stdout_log(tmp_path, "signer", "acc")
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
    assert runner.process_key("signer", "acc", tmp_path) not in runner._PROCESSES
    assert runner.process_key("signer", "acc", tmp_path) not in runner._LOCKS


def test_start_closes_log_fp_after_popen(monkeypatch, tmp_path):
    """start() 在 Popen 之后应立即关闭父进程的日志文件对象,避免 fd 泄漏。"""
    captured = {}

    class _FakeChild:
        pid = 12345

        def poll(self):
            return None  # 子进程仍在运行(成功路径)

        def wait(self, timeout=None):
            return 0

    def fake_popen(cmd, stdout=None, stderr=None, env=None):
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
    runner._PROCESSES.pop(runner.process_key("signer", "acc", tmp_path), None)
    lock = runner._LOCKS.pop(runner.process_key("signer", "acc", tmp_path), None)
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

    def fake_popen(cmd, stdout=None, stderr=None, env=None):
        return _FakeChild()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.0)

    ok, msg = runner.start("signer", "t_zombie", tmp_path, "acc")
    assert ok is False
    assert "启动后立即退出" in msg
    assert waited["called"], "早退子进程未被 wait() 收割"
    # 不应留在 _PROCESSES / _LOCKS 里
    assert runner.process_key("signer", "acc", tmp_path) not in runner._PROCESSES
    assert runner.process_key("signer", "acc", tmp_path) not in runner._LOCKS


def test_start_passes_proxy_via_env_not_argv(monkeypatch, tmp_path):
    """代理凭据必须走 TG_PROXY 环境变量,不能出现在子进程 argv 里。

    ``--proxy socks5://user:pass@host`` 同机可被 ``ps`` / 任务管理器读到明文密码,
    而 CLI 的 ``--proxy`` 本就声明了 ``envvar="TG_PROXY"``,用环境变量传递即可。
    """
    captured = {}

    class _FakeChild:
        pid = 4242

        def poll(self):
            return None  # 仍在运行 -> 成功路径

        def wait(self, timeout=None):
            return 0

    def fake_popen(cmd, stdout=None, stderr=None, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return _FakeChild()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.0)
    monkeypatch.delenv("TG_PROXY", raising=False)

    proxy = "socks5://user:secret@127.0.0.1:1080"
    ok, msg = runner.start("signer", "t_proxy", tmp_path, "acc", proxy)
    assert ok, msg

    assert "--proxy" not in captured["cmd"]
    assert not any("socks5://" in part for part in captured["cmd"])
    assert captured["env"]["TG_PROXY"] == proxy
    runner._forget(runner.process_key("signer", "acc", tmp_path))


def test_start_isolates_child_log_dir(monkeypatch, tmp_path):
    """子进程日志目录按 (kind, account) 隔离,避免多进程轮转同一份 warn/error。"""
    captured = {}

    class _FakeChild:
        pid = 4243

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def fake_popen(cmd, stdout=None, stderr=None, env=None):
        captured["cmd"] = cmd
        return _FakeChild()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.0)

    ok, msg = runner.start("automation", "t_log", tmp_path, "acc")
    assert ok, msg
    child_log_dir = tmp_path / "logs" / "automation-acc"
    assert captured["cmd"][captured["cmd"].index("--log-dir") + 1] == str(child_log_dir)
    assert captured["cmd"][captured["cmd"].index("--log-file") + 1] == str(
        child_log_dir / runner.DEFAULT_LOG_FILE_NAME
    )
    # 子进程 stdout 也隔离在同一个子目录;顶层主日志留给主进程自己的 handler。
    assert runner.child_stdout_log(tmp_path, "automation", "acc").is_file()
    assert not (tmp_path / "logs" / runner.DEFAULT_LOG_FILE_NAME).exists()
    runner._forget(runner.process_key("automation", "acc", tmp_path))


# ---------------------------------------------------------------------------
# 已退出子进程的清理 / Popen 失败 / 启动宽限期内的 stop
# ---------------------------------------------------------------------------


def test_start_after_child_exited_by_itself_releases_stale_lock(monkeypatch, tmp_path):
    """子进程自行退出后立即重启，不能报「正在被其他进程使用」。

    已死子进程的 LockHandle 仍留在 _LOCKS 里继续占着 <account>.lock
    （flock / msvcrt.locking 按打开的文件描述符记账），而只有
    running_tasks()/status()/stop() 会顺手清理它 —— 于是「子进程自己退了、
    用户马上再点启动」必然失败，错误信息还是误导性的账号占用。
    """
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(0.3)"],
    )
    ok, msg = runner.start("signer", "t_stale", tmp_path, "acc")
    assert ok, msg
    key = runner.process_key("signer", "acc", tmp_path)
    # 子进程自己退出；没有任何人 poll / stop 过它。
    runner._PROCESSES[key].wait(timeout=15)
    assert runner._PROCESSES[key].poll() is not None
    assert key in runner._LOCKS

    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    ok2, msg2 = runner.start("signer", "t_stale", tmp_path, "acc")
    assert ok2, msg2
    assert "其他进程" not in msg2
    runner.stop("signer", "acc", tmp_path)


def test_start_popen_value_error_releases_account_lock(tmp_path):
    """Popen 抛 ValueError（任务名含 NUL）时不得把账号锁漏在 _LOCKS 里。

    ``start()`` 在拉起子进程前已经抢到账号锁；只兜 OSError 时 ValueError 会带着
    锁一起冒泡，锁要到 traceback 被 GC 才释放（违反 test_account_lock.py 的
    「start 失败不得留锁」不变量）。
    """
    ok, msg = runner.start("signer", "bad\x00task", tmp_path, "acc")
    assert ok is False
    assert "启动失败" in msg
    assert runner.process_key("signer", "acc", tmp_path) not in runner._LOCKS
    assert runner.process_key("signer", "acc", tmp_path) not in runner._PROCESSES

    # 锁必须真的释放了：同一个进程再抢一次必须成功。
    lock = runner._acquire_account_lock(tmp_path, "acc")
    lock.release()


class _SlowChild:
    """假子进程：只有在被 terminate()/kill() 之后才算退出。"""

    pid = 4321

    def __init__(self):
        self.terminated = False
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.terminated = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def _start_in_thread(results, tmp_path, tasks="t_grace"):
    thread = threading.Thread(
        target=lambda: results.setdefault(
            "value", runner.start("signer", tasks, tmp_path, "acc")
        )
    )
    thread.start()
    return thread


def _wait_registered(key, timeout=0.4):
    """在启动宽限期的前半段内等子进程登记。

    timeout 必须明显小于 ``_STARTUP_GRACE_SECONDS``：只有「宽限期还没结束就已经
    登记」才算修复成功，等到宽限期结束后才登记是旧行为（那段时间里 stop 看不到它）。
    """
    deadline = time.time() + timeout
    while key not in runner._PROCESSES and time.time() < deadline:
        time.sleep(0.01)
    return key in runner._PROCESSES


def test_stop_during_startup_grace_can_still_stop_child(monkeypatch, tmp_path):
    """启动宽限期内 stop() 不能报「未在运行」而把子进程留成孤儿。

    子进程原来要等 _STARTUP_GRACE_SECONDS 之后才登记进 _PROCESSES，这段窗口里
    stop()/shutdown_all() 完全看不到它：用户看到「未在运行」，进程却已经拉起，
    且再也没人能停它。
    """
    child = _SlowChild()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 1.0)

    results = {}
    thread = _start_in_thread(results, tmp_path)
    key = runner.process_key("signer", "acc", tmp_path)
    try:
        assert _wait_registered(key), "子进程未在宽限期内登记，stop() 无从下手"
        ok, msg = runner.stop("signer", "acc", tmp_path)
        assert ok, msg
        assert child.terminated, "宽限期内拉起的子进程没有被终止，成为孤儿"
    finally:
        thread.join(timeout=10)
        runner._forget(key)

    assert runner._PROCESSES == {}
    assert runner._LOCKS == {}
    started_ok, started_msg = results["value"]
    assert started_ok is False
    assert "启动后立即退出" in started_msg


def test_shutdown_all_during_startup_grace_stops_child(monkeypatch, tmp_path):
    """shutdown_all() 同样必须覆盖启动宽限期内的子进程（WebUI 关闭不留孤儿）。"""
    child = _SlowChild()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 1.0)

    results = {}
    thread = _start_in_thread(results, tmp_path)
    key = runner.process_key("signer", "acc", tmp_path)
    try:
        assert _wait_registered(key), "子进程未在宽限期内登记，shutdown_all() 无从下手"
        assert runner.shutdown_all(timeout=1.0) == [runner.display_key("signer", "acc")]
        assert child.terminated
    finally:
        thread.join(timeout=10)
        runner._forget(key)

    assert runner._PROCESSES == {}
    assert runner._LOCKS == {}


def test_forget_guarded_by_identity_spares_newer_process(tmp_path):
    """并发 start/stop 交错时，晚到的一方的 _forget 不能误删别人刚登记的进程。

    start() 现在会在发现「已退出的旧子进程」时先 _forget 再抢锁，stop() /
    running_tasks() 也在等待/轮询后才清理；如果清理不校验身份，晚到的一方可
    把对方刚登记的新子进程连同账号锁一起删掉，同账号随即出现两个写者。
    """
    key = runner.process_key("signer", "acc", tmp_path)
    old = _SlowChild()
    new = _SlowChild()
    lock = runner._acquire_account_lock(tmp_path, "acc")
    with runner._STATE_LOCK:
        runner._PROCESSES[key] = new
        runner._LOCKS[key] = lock
        runner._TASK_NAMES[key] = ["new"]

    runner._forget(key, expected=old)
    assert runner._PROCESSES[key] is new
    assert runner._LOCKS[key] is lock
    assert runner._TASK_NAMES[key] == ["new"]

    runner._forget(key, expected=new)
    assert key not in runner._PROCESSES
    assert key not in runner._LOCKS
    assert key not in runner._TASK_NAMES


def test_running_queries_can_be_scoped_to_one_workdir(monkeypatch, tmp_path):
    """``running_tasks`` / ``running_task_names`` 必须能按 workdir 过滤。

    回归：这两个函数原先没有 workdir 参数，把注册表里的进程全列了出来，而
    ``run_stop`` 用的是**当前**目录去解析 key。于是切换工作目录后，旧目录里仍在
    跑的任务继续显示「运行中」，用户点每一行的「停止」都只回一句「未在运行」
    —— 列表上的按钮全废。
    """
    monkeypatch.setattr(runner, "_STARTUP_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    workdir_a = tmp_path / "a"
    workdir_b = tmp_path / "b"
    ok, msg = runner.start("signer", "daily", workdir_a, "acc")
    assert ok, msg
    try:
        assert runner.running_tasks(workdir_a) == {"signer:acc": True}
        assert runner.running_task_names(workdir_a) == {"signer:acc": ["daily"]}
        # 另一个目录：什么都不该有
        assert runner.running_tasks(workdir_b) == {}
        assert runner.running_task_names(workdir_b) == {}
        # 不传 workdir 仍是全量语义（关机清理等调用方要的就是这个）
        assert runner.running_tasks() == {"signer:acc": True}
        assert runner.running_task_names() == {"signer:acc": ["daily"]}
    finally:
        runner.stop("signer", "acc", workdir_a)
