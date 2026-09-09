"""End-to-end test for the unified logging pipeline.

Exercises the full path that real WebUI traffic takes:

1. ``webui.data._setup_webui_logger`` configures file logging for the WebUI
   process itself.
2. ``webui.runner.start`` spawns a child process whose stdout/stderr is
   appended to the same ``<workdir>/logs/tg-signer.log``.
3. ``webui.data.load_logs`` reads that file from the WebUI log page.

Each test is isolated with a logger-handler snapshot so the global
``logging.getLogger("tg-signer")`` singleton does not leak state into
other tests.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tg_signer.webui import data as webui_data
from tg_signer.webui import runner as webui_runner
from tg_signer.webui.data import _setup_webui_logger


@pytest.fixture
def restored_logger():
    """Snapshot/restore the global ``tg-signer`` logger handlers around a test.

    ``configure_logger`` calls ``logger.handlers.clear()`` then re-adds
    handlers; we must not leak that mutation into other tests.
    """
    logger = logging.getLogger("tg-signer")
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    saved_propagate = logger.propagate
    try:
        yield logger
    finally:
        logger.handlers.clear()
        for h in saved_handlers:
            logger.addHandler(h)
        logger.setLevel(saved_level)
        logger.propagate = saved_propagate


@pytest.fixture
def _webui_process_state():
    """Make sure no orphaned child processes survive the test."""
    yield
    for key, proc in list(webui_runner._PROCESSES.items()):
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        webui_runner._PROCESSES.pop(key, None)
        lock = webui_runner._LOCKS.pop(key, None)
        if lock is not None:
            lock.release()


def test_setup_webui_logger_creates_main_log(tmp_path, restored_logger):
    """``_setup_webui_logger`` 应创建 <workdir>/logs/tg-signer.log 并配 file handler。"""
    _setup_webui_logger(tmp_path)

    main_log = tmp_path / "logs" / webui_runner.DEFAULT_LOG_FILE_NAME
    assert main_log.is_file(), f"main log not created at {main_log}"

    logger = logging.getLogger("tg-signer")
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert any(
        Path(h.baseFilename).resolve() == main_log.resolve()  # type: ignore[attr-defined]
        for h in file_handlers
    ), "no file handler points at the unified main log"

    # WebUI 自身写一行 INFO,确认真的落到主日志
    logger.info("WEBUI_E2E_MARKER")
    for _ in range(20):
        if "WEBUI_E2E_MARKER" in main_log.read_text(encoding="utf-8", errors="ignore"):
            break
        time.sleep(0.05)
    assert "WEBUI_E2E_MARKER" in main_log.read_text(encoding="utf-8", errors="ignore")


def test_child_process_stdout_visible_in_load_logs(
    tmp_path, restored_logger, _webui_process_state, monkeypatch
):
    """起一个真子进程写 stdout,确认 data.load_logs 能从主日志读出来。"""
    # 1) WebUI 自身 logger 初始化
    _setup_webui_logger(tmp_path)
    main_log = tmp_path / "logs" / webui_runner.DEFAULT_LOG_FILE_NAME

    # 2) 缩短 grace,子进程先 flush marker 再 sleep 60
    monkeypatch.setattr(webui_runner, "_STARTUP_GRACE_SECONDS", 0.3)
    marker = "E2E_CHILD_STDOUT_42"
    child_script = (
        "import sys, time; "
        "sys.stdout.write('" + marker + "\\n'); "
        "sys.stdout.flush(); time.sleep(60)"
    )
    monkeypatch.setattr(
        webui_runner,
        "build_command",
        lambda *a, **k: [sys.executable, "-c", child_script],
    )

    ok, msg = webui_runner.start("signer", "t_e2e", tmp_path, "acc")
    assert ok, msg
    try:
        # 3) 等待 marker 落盘
        deadline = time.time() + 10
        while time.time() < deadline:
            content = main_log.read_text(encoding="utf-8", errors="ignore")
            if marker in content:
                break
            time.sleep(0.05)

        # 4) 模拟 WebUI 日志页:用 data.load_logs 读主日志
        resolved_path, lines = webui_data.load_logs(limit=1000, log_path=str(main_log))
        assert resolved_path == main_log
        assert any(marker in line for line in lines), (
            f"load_logs did not surface child stdout; lines were:\n{lines!r}"
        )
    finally:
        webui_runner.stop("signer", "acc")


def test_ui_state_log_path_defaults_to_workdir_main_log():
    """UIState.log_path 默认应指向 workdir/logs/tg-signer.log。

    直接实例化 UIState(无 nicegui 渲染),验证默认 workdir 化的主日志路径。
    """
    from tg_signer.webui.data import UIState

    state = UIState()
    assert state.log_path == state.workdir / "logs" / webui_data.LOG_FILE_NAME
    assert state.log_path.name == "tg-signer.log"

    # 切 workdir 时,log_path 跟着切
    new_workdir = state.workdir.parent / "another_workdir"
    state.set_workdir(str(new_workdir))
    assert state.workdir == new_workdir
    assert state.log_path == new_workdir / "logs" / webui_data.LOG_FILE_NAME
