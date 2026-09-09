"""WebUI 后台运行进程管理。

以独立 CLI 子进程持续运行签到/监控/自动化任务，避免阻塞 WebUI 事件循环。
所有子进程与 WebUI 主进程统一写入 <workdir>/logs/<DEFAULT_LOG_FILE>，
子进程 stdout/stderr 也追加到同一文件，避免日志被 DEVNULL 吞掉。

**单账号多任务共享一个子进程**: 同 `(kind, account)` 的多个任务在同一个
子进程内通过 `asyncio.gather` 跑，共享同一个 pyrogram Client，从而避免多个
进程抢同一份 `<workdir>/<account>.session` SQLite 文件触发
``sqlite3.OperationalError: database is locked``。**跨进程/跨 WebUI 实例
的兜底**则由 ``<workdir>/<account>.lock`` 文件锁提供，``runner.start`` 在拉
起子进程前以非阻塞方式抢占独占锁，失败即拒绝启动，防止两个 WebUI 同时操作
同一账号。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# 与 webui.data.DEFAULT_LOG_FILE.name 保持一致,统一主日志文件名
DEFAULT_LOG_FILE_NAME = "tg-signer.log"

_PROCESSES: Dict[str, subprocess.Popen] = {}
# 账号级文件锁: key = process_key(kind, account) -> 持有锁的文件对象。
# 子进程退出 / runner.stop / runner.shutdown_all 时必须释放,否则同账号
# 无法再启动任何任务。POSIX 上 flock 是 advisory,Windows 上 msvcrt.locking
# 是 mandatory;跨平台都依赖 OS 在进程退出时关闭所有 fd → 锁自动释放。
_LOCKS: Dict[str, "LockHandle"] = {}

# 启动后等待子进程就绪的秒数,用于尽早捕获启动失败(参数错误、session 无效等)
_STARTUP_GRACE_SECONDS = 1.5  # Windows 进程启动通常需要 0.5-1.5s


# ---------------------------------------------------------------------------
# 文件锁(跨平台)
# ---------------------------------------------------------------------------


class AccountLocked(Exception):
    """账号级文件锁被其他进程持有时抛出。"""


class LockHandle:
    """对账号级锁文件 fd 的薄封装,统一 lock/unlock 语义。"""

    __slots__ = ("fp", "_locked")

    def __init__(self, fp):
        self.fp = fp
        self._locked = True

    def release(self) -> None:
        if not self._locked:
            return
        self._locked = False
        try:
            _unlock(self.fp)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.fp.close()
        except Exception:  # noqa: BLE001
            pass


def _try_lock(fp) -> bool:
    """非阻塞独占锁,失败返回 False。POSIX 用 flock,Windows 用 msvcrt.locking。"""
    if os.name == "posix":
        import fcntl

        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False
    if os.name == "nt":
        import msvcrt

        try:
            # msvcrt.locking 要求文件以二进制模式打开且至少有 1 字节内容
            msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except (BlockingIOError, OSError):
            return False
    # 其他平台:best-effort no-op
    return True


def _unlock(fp) -> None:
    if os.name == "posix":
        import fcntl

        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        except Exception:  # noqa: BLE001
            pass
    elif os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:  # noqa: BLE001
            pass


def _acquire_account_lock(workdir: Path, account: str) -> LockHandle:
    """抢占 <workdir>/<account>.lock 的独占锁。

    失败抛 ``AccountLocked``;成功返回 ``LockHandle``,调用方需负责在子进程
    退出 / stop / shutdown 时调用 ``release()``。
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    lock_path = workdir / f"{account}.lock"
    # 确保文件存在且至少 1 字节(msvcrt.locking 需要)
    if not lock_path.exists():
        try:
            lock_path.touch()
        except OSError:
            pass
    fp = open(lock_path, "r+b")
    if not _try_lock(fp):
        try:
            fp.close()
        except Exception:  # noqa: BLE001
            pass
        raise AccountLocked(f"账号 {account} 正在被其他进程使用")
    # 注意: Windows 上 msvcrt.locking 是 mandatory,持锁期间其他进程
    # 连 read 都会被拒(PermissionError),所以不向锁文件写 PID(防止
    # 诊断工具读不到);如需排查死锁,通过 lsof / procexp 看 fd 持有者即可。
    return LockHandle(fp)


# ---------------------------------------------------------------------------
# 进程 key / 命令构造
# ---------------------------------------------------------------------------


def process_key(kind: str, account: str) -> str:
    """单进程 per (kind, account) — 同账号同 kind 的多任务合并到一个子进程。"""
    return f"{kind}:{account}"


def build_command(
    kind: str,
    tasks: Union[str, List[str]],
    workdir: Path | str,
    account: str,
    proxy: Optional[str] = None,
) -> List[str]:
    """构造启动子进程的 CLI 命令。

    ``tasks`` 接受单任务名(str)或任务列表(List[str])。所有任务共享一个
    子进程,通过 ``asyncio.gather`` 并发运行(共享 Client / 同一 SQLite 会话)。
    """
    if isinstance(tasks, str):
        tasks = [tasks]
    if not tasks:
        raise ValueError("至少需要一个任务名")
    workdir = Path(workdir)
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
        cmd += ["run", *tasks]
    elif kind == "monitor":
        cmd += ["monitor", "run", *tasks]
    elif kind == "automation":
        cmd += ["automation", "run", *tasks]
    else:
        raise ValueError(f"不支持的运行类型: {kind}")
    return cmd


# ---------------------------------------------------------------------------
# 进程管理(start / stop / status / running_tasks / shutdown_all)
# ---------------------------------------------------------------------------


def running_tasks() -> Dict[str, bool]:
    """返回 {process_key: is_running},并清理已退出条目。"""
    result: Dict[str, bool] = {}
    for key, proc in list(_PROCESSES.items()):
        if proc.poll() is None:
            result[key] = True
        else:
            _PROCESSES.pop(key, None)
            lock = _LOCKS.pop(key, None)
            if lock is not None:
                lock.release()
            result[key] = False
    return result


def status(kind: str, account: str) -> bool:
    """``(kind, account)`` 对应的子进程是否仍在运行。"""
    key = process_key(kind, account)
    proc = _PROCESSES.get(key)
    if proc is None:
        return False
    if proc.poll() is not None:
        _PROCESSES.pop(key, None)
        lock = _LOCKS.pop(key, None)
        if lock is not None:
            lock.release()
        return False
    return True


def start(
    kind: str,
    tasks: Union[str, List[str]],
    workdir: Path | str,
    account: str,
    proxy: Optional[str] = None,
) -> Tuple[bool, str]:
    """为 ``(kind, account)`` 拉起一个子进程,在其中跑 ``tasks`` 的全部任务。

    同 ``(kind, account)`` 已有进程在跑时,直接返回「已在运行」;新任务列表如
    果是当前列表的超集,亦按 no-op 处理(避免覆盖用户当前任务)。其余情况
    必须先 ``stop`` 再 ``start``。
    """
    if isinstance(tasks, str):
        tasks = [tasks]
    if not tasks:
        return False, "需要至少一个任务名"
    key = process_key(kind, account)
    proc = _PROCESSES.get(key)
    if proc is not None and proc.poll() is None:
        return False, f"账号 {account} 的 {kind} 任务已在运行 (PID {proc.pid})"
    workdir = Path(workdir)

    # 抢账号级文件锁(防止跨 WebUI 实例并发启动同账号)
    try:
        lock = _acquire_account_lock(workdir, account)
    except AccountLocked as exc:
        return False, str(exc)
    except OSError as exc:
        return False, f"获取账号锁失败: {exc}"

    log_dir = workdir / "logs"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_command(kind, tasks, workdir, account, proxy)
        main_log = log_dir / DEFAULT_LOG_FILE_NAME
        log_fp = open(main_log, "a", encoding="utf-8")
    except OSError as exc:
        lock.release()
        return False, f"{tasks[0]} 启动失败: {exc}"
    except ValueError as exc:
        lock.release()
        return False, str(exc)
    try:
        child = subprocess.Popen(cmd, stdout=log_fp, stderr=log_fp)
    except OSError as exc:
        log_fp.close()
        lock.release()
        return False, f"{tasks[0]} 启动失败: {exc}"

    # 子进程通过句柄继承拿到了自己的写入端,父进程应立即释放这个 Python 文件
    # 对象,否则每次 start() 泄漏一个 fd:长会话反复启停会累积到系统上限,且在
    # Windows 下父进程残留的句柄会让日志文件无法被轮转/重命名(PermissionError)。
    log_fp.close()

    # 早期失败检测:短暂 wait + poll,如果子进程已退出,说明参数错误/启动异常
    time.sleep(_STARTUP_GRACE_SECONDS)
    rc = child.poll()
    if rc is not None:
        # 收割已退出的子进程,避免 POSIX 下残留僵尸进程
        child.wait()
        lock.release()
        task_disp = (
            tasks[0] if len(tasks) == 1 else f"{tasks[0]} 等 {len(tasks)} 个任务"
        )
        return False, (
            f"{task_disp} 启动后立即退出(exit code={rc}),请检查 session 与参数"
        )

    _PROCESSES[key] = child
    _LOCKS[key] = lock
    task_disp = tasks[0] if len(tasks) == 1 else f"{len(tasks)} 个任务"
    return True, f"{kind} 任务 {task_disp} 已启动 (PID {child.pid})"


def stop(kind: str, account: str) -> Tuple[bool, str]:
    key = process_key(kind, account)
    proc = _PROCESSES.get(key)
    if proc is None or proc.poll() is not None:
        _PROCESSES.pop(key, None)
        lock = _LOCKS.pop(key, None)
        if lock is not None:
            lock.release()
        return False, f"账号 {account} 的 {kind} 任务未在运行"
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    _PROCESSES.pop(key, None)
    lock = _LOCKS.pop(key, None)
    if lock is not None:
        lock.release()
    return True, f"账号 {account} 的 {kind} 任务已停止"


def shutdown_all(timeout: float = 5.0) -> List[str]:
    """Terminate all tracked child processes and release their locks.

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
        lock = _LOCKS.pop(key, None)
        if lock is not None:
            lock.release()
        stopped.append(key)
    return stopped
