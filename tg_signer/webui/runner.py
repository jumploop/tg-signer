"""WebUI 后台运行进程管理。

以独立 CLI 子进程持续运行签到/监控任务，避免阻塞 WebUI 事件循环。
所有子进程与 WebUI 主进程统一写入 <workdir>/logs/<DEFAULT_LOG_FILE>，
子进程 stdout/stderr 也追加到同一文件，避免日志被 DEVNULL 吞掉。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 与 webui.data.DEFAULT_LOG_FILE.name 保持一致,统一主日志文件名
DEFAULT_LOG_FILE_NAME = "tg-signer.log"

_PROCESSES: Dict[str, subprocess.Popen] = {}

# 启动后等待子进程就绪的秒数,用于尽早捕获启动失败(参数错误、session 无效等)
_STARTUP_GRACE_SECONDS = 1.5  # Windows 进程启动通常需要 0.5-1.5s


def process_key(kind: str, task: str) -> str:
    return f"{kind}:{task}"


def log_path(workdir: Path | str, kind: str, task: str) -> Path:
    """Return the per-task log file path.

    .. deprecated::
        0.9.9 起所有日志统一到 <workdir>/logs/<DEFAULT_LOG_FILE_NAME>,
        本函数仅保留兼容旧调用方,返回主日志文件路径。
    """
    return Path(workdir) / "logs" / DEFAULT_LOG_FILE_NAME


def build_command(
    kind: str,
    task: str,
    workdir: Path | str,
    account: str,
    proxy: Optional[str] = None,
) -> List[str]:
    """Construct the CLI command that keeps running <kind> task <task>."""
    workdir = Path(workdir)
    # 统一写到 <workdir>/logs/tg-signer.log(WebUI 主进程也写同一份),便于日志页聚合
    cmd = [
        sys.executable,
        "-m",
        "tg_signer",
        "--workdir",
        str(workdir),
        "--account",
        account,
        "--session_dir",
        str(workdir),
        "--log-dir",
        str(workdir / "logs"),
    ]
    if proxy:
        cmd += ["--proxy", proxy]
    if kind == "signer":
        cmd += ["run", task]
    elif kind == "monitor":
        cmd += ["monitor", "run", task]
    elif kind == "automation":
        cmd += ["automation", "run", task]
    else:
        raise ValueError(f"不支持的运行类型: {kind}")
    return cmd


def running_tasks() -> Dict[str, bool]:
    """Return {process_key: is_running} and drop finished entries."""
    result: Dict[str, bool] = {}
    for key, proc in list(_PROCESSES.items()):
        if proc.poll() is None:
            result[key] = True
        else:
            _PROCESSES.pop(key, None)
            result[key] = False
    return result


def status(kind: str, task: str) -> bool:
    """Return True if the process for (kind, task) is still alive."""
    key = process_key(kind, task)
    proc = _PROCESSES.get(key)
    if proc is None:
        return False
    if proc.poll() is not None:
        _PROCESSES.pop(key, None)
        return False
    return True


def start(
    kind: str,
    task: str,
    workdir: Path | str,
    account: str,
    proxy: Optional[str] = None,
) -> Tuple[bool, str]:
    key = process_key(kind, task)
    proc = _PROCESSES.get(key)
    if proc is not None and proc.poll() is None:
        return False, f"{task} 已在运行"
    workdir = Path(workdir)
    log_dir = workdir / "logs"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_command(kind, task, workdir, account, proxy)
        # 把 stdout/stderr 也追加到同一份主日志,作为 file handler 的双保险
        # (多进程并发写同一文件在 logging 层是线程安全的;跨进程这里仅作 fallback)
        main_log = log_dir / DEFAULT_LOG_FILE_NAME
        log_fp = open(main_log, "a", encoding="utf-8")
    except OSError as exc:
        return False, f"{task} 启动失败: {exc}"
    try:
        child = subprocess.Popen(cmd, stdout=log_fp, stderr=log_fp)
    except OSError as exc:
        log_fp.close()
        return False, f"{task} 启动失败: {exc}"

    # 早期失败检测:短暂 wait + poll,如果子进程已退出,说明参数错误/启动异常
    time.sleep(_STARTUP_GRACE_SECONDS)
    rc = child.poll()
    if rc is not None:
        return False, f"{task} 启动后立即退出(exit code={rc}),请检查 session 与参数"

    _PROCESSES[key] = child
    return True, f"{task} 已启动 (PID {child.pid})"


def stop(kind: str, task: str) -> Tuple[bool, str]:
    key = process_key(kind, task)
    proc = _PROCESSES.get(key)
    if proc is None or proc.poll() is not None:
        _PROCESSES.pop(key, None)
        return False, f"{task} 未在运行"
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    _PROCESSES.pop(key, None)
    return True, f"{task} 已停止"


def shutdown_all(timeout: float = 5.0) -> List[str]:
    """Terminate all tracked child processes.

    Intended to be called from a WebUI shutdown hook so that children do
    not become orphans when the WebUI process exits. Returns the list of
    stopped process keys.
    """
    stopped: List[str] = []
    for key, proc in list(_PROCESSES.items()):
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=timeout)
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001
                pass
        _PROCESSES.pop(key, None)
        stopped.append(key)
    return stopped
