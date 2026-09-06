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
        runner._PROCESSES.pop(key, None)


def test_process_key_and_log_path(tmp_path):
    assert runner.process_key("signer", "my_sign") == "signer:my_sign"
    assert runner.log_path(tmp_path, "signer", "my_sign") == (
        tmp_path / "logs" / "signer_my_sign.log"
    )


def test_build_command_signer(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner, "sys", type("FakeSys", (), {"executable": "/usr/bin/python"})
    )
    cmd = runner.build_command("signer", "my_sign", tmp_path, "acc1")
    assert cmd[0] == "/usr/bin/python"
    assert cmd[1:4] == ["-m", "tg_signer", "--workdir"]
    assert "--account" in cmd
    assert "--session_dir" in cmd
    assert "--log-dir" in cmd
    log_file = cmd[cmd.index("--log-file") + 1]
    assert Path(log_file) == tmp_path / "logs" / "signer_my_sign.log"
    assert cmd[-2:] == ["run", "my_sign"]


def test_build_command_kinds_proxy_and_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "sys", type("FakeSys", (), {"executable": "py"}))
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
    cmd = runner.build_command("signer", "s1", tmp_path, "a", proxy="socks5://x:1")
    assert cmd[cmd.index("--proxy") :] == ["--proxy", "socks5://x:1", "run", "s1"]
    with pytest.raises(ValueError):
        runner.build_command("unknown", "t", tmp_path, "a")


def test_start_then_stop(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    ok, msg = runner.start("signer", "t1", tmp_path, "acc")
    assert ok
    key = runner.process_key("signer", "t1")
    assert runner.running_tasks().get(key) is True

    ok_dup, _msg = runner.start("signer", "t1", tmp_path, "acc")
    assert not ok_dup

    ok_stop, _msg = runner.stop("signer", "t1")
    assert ok_stop
    assert runner.running_tasks().get(key) is not True
    ok_stop_again, _msg = runner.stop("signer", "t1")
    assert not ok_stop_again


def test_running_tasks_cleans_finished(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "pass"],
    )
    runner.start("signer", "t2", tmp_path, "acc")
    deadline = time.time() + 10
    while runner.running_tasks().get("signer:t2", True) and time.time() < deadline:
        time.sleep(0.05)
    assert "signer:t2" not in runner.running_tasks()


def test_status_tracks_process_lifecycle(monkeypatch, tmp_path):
    assert runner.status("signer", "t3") is False

    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    runner.start("signer", "t3", tmp_path, "acc")
    assert runner.status("signer", "t3") is True

    ok, _msg = runner.stop("signer", "t3")
    assert ok
    assert runner.status("signer", "t3") is False

    monkeypatch.setattr(
        runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", "pass"],
    )
    runner.start("signer", "t4", tmp_path, "acc")
    deadline = time.time() + 10
    while runner.status("signer", "t4") and time.time() < deadline:
        time.sleep(0.05)
    assert runner.status("signer", "t4") is False
