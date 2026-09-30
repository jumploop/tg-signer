"""WebUI 后台运行进程管理。

以独立 CLI 子进程持续运行签到/监控/自动化任务，避免阻塞 WebUI 事件循环。
WebUI 主进程自身的日志写入 <workdir>/logs/<DEFAULT_LOG_FILE>；每个任务子进程
则独占 <workdir>/logs/<kind>-<account>/，它的 logger 与 stdout/stderr 都在那里，
两者互不干扰（主日志的 RotatingFileHandler 一旦轮转，子进程的裸 fd 会因指向
旧 inode 而静默丢日志）。

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
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from tg_signer.utils import resolve_under

# 与 webui.data.DEFAULT_LOG_FILE.name 保持一致,统一主日志文件名
DEFAULT_LOG_FILE_NAME = "tg-signer.log"

# 下面三个字典由 FastAPI 的线程池并发读写(每个请求一个线程),所有读写都必须
# 经过 _STATE_LOCK。用 RLock 而不是 Lock:_forget() 会被已经持锁的调用方再次
# 进入。锁只覆盖字典操作本身,不覆盖 _STARTUP_GRACE_SECONDS 这类阻塞等待。
_STATE_LOCK = threading.RLock()
_PROCESSES: Dict[str, subprocess.Popen] = {}
# 账号级文件锁: key = process_key(kind, account) -> 持有锁的文件对象。
# 子进程退出 / runner.stop / runner.shutdown_all 时必须释放,否则同账号
# 无法再启动任何任务。POSIX 上 flock 是 advisory,Windows 上 msvcrt.locking
# 是 mandatory;跨平台都依赖 OS 在进程退出时关闭所有 fd → 锁自动释放。
_LOCKS: Dict[str, "LockHandle"] = {}
# 每个进程 key 实际启动的任务名,供 WebUI 展示"当前在跑哪些任务"。
_TASK_NAMES: Dict[str, List[str]] = {}

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

    失败抛 ``AccountLocked``;账号名越界抛 ``ValueError``;成功返回
    ``LockHandle``,调用方需负责在子进程退出 / stop / shutdown 时调用
    ``release()``。
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    lock_path = resolve_under(workdir, account, suffix=".lock")
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


# ``_forget`` 的默认期望值：不校验当前登记的是哪个进程，无条件清理。
_ANY_PROCESS = object()


def _forget(key: str, expected: Any = _ANY_PROCESS) -> None:
    """清理 key 对应的进程 / 锁 / 任务名,并释放锁。

    ``expected`` 给定时只在 ``_PROCESSES[key]`` 正是它（或 ``None``：要求该 key
    当前没有登记进程）时才清理。并发 start()/stop() 交错时，晚到的一方才不会把
    对方刚登记的新子进程连同账号锁一起误删 —— 锁一释放，同账号就会出现两个
    写者，正是这个锁要防的事情。``_STATE_LOCK`` 内的「比较并清理」是原子的。
    """
    with _STATE_LOCK:
        if expected is not _ANY_PROCESS and _PROCESSES.get(key) is not expected:
            return
        _PROCESSES.pop(key, None)
        _TASK_NAMES.pop(key, None)
        lock = _LOCKS.pop(key, None)
    if lock is not None:
        # 释放文件锁放到字典锁之外:release() 里有系统调用,不该拖住其它查询。
        lock.release()


# ---------------------------------------------------------------------------
# 进程 key / 命令构造
# ---------------------------------------------------------------------------


def process_key(kind: str, account: str) -> str:
    """单进程 per (kind, account) — 同账号同 kind 的多任务合并到一个子进程。"""
    return f"{kind}:{account}"


def child_log_dir(workdir: Path | str, kind: str, account: str) -> Path:
    """任务子进程独占的日志目录 ``<workdir>/logs/<kind>-<account>/``。"""
    return resolve_under(Path(workdir) / "logs", f"{kind}-{account}")


def child_stdout_log(workdir: Path | str, kind: str, account: str) -> Path:
    """子进程 stdout/stderr 的落点。

    曾经指向顶层 ``<workdir>/logs/tg-signer.log``，于是主日志同时有两个写入方：
    WebUI 主进程的 ``RotatingFileHandler`` 和子进程经 ``Popen`` 继承的裸 fd。
    轮转时主进程把文件改名成 ``.log.1`` 并新建，子进程那个 fd 仍指着改名前的旧
    inode，此后所有输出都落进 ``.log.1`` —— 从「运行日志」页看主日志就是
    「任务跑了一段时间后突然不再更新」。子进程自己的 logger 已经在写这个子目录，
    stdout 再抄一份到主日志本就是冗余，直接隔离到同一子目录即可。
    """
    return child_log_dir(workdir, kind, account) / "stdout.log"


def build_command(
    kind: str,
    tasks: Union[str, List[str]],
    workdir: Path | str,
    account: str,
) -> List[str]:
    """构造启动子进程的 CLI 命令。

    ``tasks`` 接受单任务名(str)或任务列表(List[str])。所有任务共享一个
    子进程,通过 ``asyncio.gather`` 并发运行(共享 Client / 同一 SQLite 会话)。

    两点刻意为之:

    - **代理不进 argv**。``--proxy socks5://user:pass@host`` 同机可被 ``ps`` /
      任务管理器读到明文凭据,改由 :func:`build_env` 通过 ``TG_PROXY`` 传入
      (CLI 的 ``--proxy`` 本就声明了 ``envvar="TG_PROXY"``)。
    - **日志目录按子进程隔离**。原来只传 ``--log-dir`` 而不传 ``--log-file``,
      CLI 的 ``--log-file`` 默认值是相对路径 ``logs/tg-signer.log``,于是子进程
      会在自己的 cwd 下另建一份 ``logs/``,而 ``warn.log`` / ``error.log`` 又被
      所有子进程共享 —— 多个 RotatingFileHandler 并发轮转会互相截断。现在把
      两个路径都指到 ``<workdir>/logs/<kind>-<account>/``；子进程的 stdout/stderr
      也重定向到同一子目录（见 :func:`child_stdout_log`），不与主日志争抢。
    """
    if isinstance(tasks, str):
        tasks = [tasks]
    if not tasks:
        raise ValueError("至少需要一个任务名")
    workdir = Path(workdir)
    log_dir = child_log_dir(workdir, kind, account)
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
        str(log_dir),
        "--log-file",
        str(log_dir / DEFAULT_LOG_FILE_NAME),
    ]
    if kind == "signer":
        cmd += ["run", *tasks]
    elif kind == "automation":
        cmd += ["automation", "run", *tasks]
    else:
        raise ValueError(f"不支持的运行类型: {kind}")
    return cmd


def build_env(proxy: Optional[str] = None) -> Dict[str, str]:
    """子进程环境:代理凭据只经 ``TG_PROXY`` 传递,不落进 argv。"""
    env = dict(os.environ)
    if proxy:
        env["TG_PROXY"] = proxy
    return env


# ---------------------------------------------------------------------------
# 进程管理(start / stop / status / running_tasks / shutdown_all)
# ---------------------------------------------------------------------------


def running_tasks() -> Dict[str, bool]:
    """返回 {process_key: is_running},并清理已退出条目。"""
    result: Dict[str, bool] = {}
    with _STATE_LOCK:
        snapshot = list(_PROCESSES.items())
    for key, proc in snapshot:
        if proc.poll() is None:
            result[key] = True
        else:
            _forget(key, expected=proc)
            result[key] = False
    return result


def running_task_names() -> Dict[str, List[str]]:
    """返回 {process_key: 任务名列表},仅包含仍在运行的进程。"""
    result: Dict[str, List[str]] = {}
    with _STATE_LOCK:
        snapshot = list(_PROCESSES.items())
        names = {key: list(_TASK_NAMES.get(key, [])) for key, _ in snapshot}
    for key, proc in snapshot:
        if proc.poll() is None:
            result[key] = names[key]
    return result


def status(kind: str, account: str) -> bool:
    """``(kind, account)`` 对应的子进程是否仍在运行。"""
    key = process_key(kind, account)
    with _STATE_LOCK:
        proc = _PROCESSES.get(key)
    if proc is None:
        return False
    if proc.poll() is not None:
        _forget(key, expected=proc)
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
    with _STATE_LOCK:
        proc = _PROCESSES.get(key)
        running = proc is not None and proc.poll() is None
    if running:
        return False, f"账号 {account} 的 {kind} 任务已在运行 (PID {proc.pid})"
    if proc is not None:
        # 子进程已自行退出，但没有任何人 poll 过它：它的 LockHandle 还留在
        # _LOCKS 里继续占着 <account>.lock（flock / msvcrt.locking 是按打开的
        # 文件描述符记账的），下面重新抢锁必然失败，报错还是误导性的
        # 「正在被其他进程使用」。旧实现只把它留给 running_tasks()/status()/
        # stop() 顺手清理，于是「子进程自己退了、用户马上点启动」永远起不来。
        # expected=proc：并发 start 可能已经登记了新子进程，不能连它一起清掉。
        _forget(key, expected=proc)
    workdir = Path(workdir)

    # 抢账号级文件锁(防止跨 WebUI 实例并发启动同账号)
    try:
        lock = _acquire_account_lock(workdir, account)
    except AccountLocked as exc:
        return False, str(exc)
    except ValueError as exc:
        # 账号名不是单一路径分量,拒绝启动(否则锁文件 / session 会落到 workdir 之外)。
        return False, str(exc)
    except OSError as exc:
        return False, f"获取账号锁失败: {exc}"

    log_dir = workdir / "logs"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_command(kind, tasks, workdir, account)
        # 落到子进程独占的子目录，而不是顶层主日志 —— 顶层主日志由主进程的
        # RotatingFileHandler 独占，混进子进程的裸 fd 会在轮转后写进旧 inode。
        stdout_log = child_stdout_log(workdir, kind, account)
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(stdout_log, "a", encoding="utf-8")
    except OSError as exc:
        lock.release()
        return False, f"{tasks[0]} 启动失败: {exc}"
    except ValueError as exc:
        lock.release()
        return False, str(exc)
    try:
        child = subprocess.Popen(
            cmd, stdout=log_fp, stderr=log_fp, env=build_env(proxy)
        )
    except (OSError, ValueError) as exc:
        # ValueError：任务名里嵌入 NUL 之类的非法参数由 subprocess 自己抛出。
        # 只兜 OSError 时它会带着已持有的账号锁一起向上冒泡，锁要到 traceback
        # 被 GC 才释放（违反 test_account_lock.py 的「start 失败不得留锁」不变量）。
        log_fp.close()
        lock.release()
        return False, f"{tasks[0]} 启动失败: {exc}"

    # 子进程通过句柄继承拿到了自己的写入端,父进程应立即释放这个 Python 文件
    # 对象,否则每次 start() 泄漏一个 fd:长会话反复启停会累积到系统上限,且在
    # Windows 下父进程残留的句柄会让日志文件无法被轮转/重命名(PermissionError)。
    log_fp.close()

    # 必须赶在宽限期睡眠之前登记：stop()/shutdown_all() 只认 _PROCESSES，晚登记
    # 的话这段窗口内拉起的子进程既停不掉、又会作为孤儿继续跑（用户看到的是
    # 「未在运行」，实际进程还活着）。
    with _STATE_LOCK:
        _PROCESSES[key] = child
        _LOCKS[key] = lock
        _TASK_NAMES[key] = list(tasks)

    # 早期失败检测:短暂 wait + poll,如果子进程已退出,说明参数错误/启动异常
    time.sleep(_STARTUP_GRACE_SECONDS)
    rc = child.poll()
    if rc is not None:
        # 收割已退出的子进程,避免 POSIX 下残留僵尸进程
        child.wait()
        # 用 _forget 而不是 lock.release():stop() 可能已经赢了这场竞态并清理过
        # 条目（_forget 幂等），重复 release 也没问题，但这样不会误留字典项。
        # expected=child：只清理自己这个子进程，不误删别人刚登记的。
        _forget(key, expected=child)
        task_disp = (
            tasks[0] if len(tasks) == 1 else f"{tasks[0]} 等 {len(tasks)} 个任务"
        )
        return False, (
            f"{task_disp} 启动后立即退出(exit code={rc}),请检查 session 与参数"
        )

    task_disp = tasks[0] if len(tasks) == 1 else f"{len(tasks)} 个任务"
    return True, f"{kind} 任务 {task_disp} 已启动 (PID {child.pid})"


def stop(kind: str, account: str) -> Tuple[bool, str]:
    key = process_key(kind, account)
    with _STATE_LOCK:
        proc = _PROCESSES.get(key)
    if proc is None or proc.poll() is not None:
        _forget(key, expected=proc)
        return False, f"账号 {account} 的 {kind} 任务未在运行"
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    # 只有确认子进程已退出(或已被 kill)才释放账号锁:锁一释放,新进程就会
    # 去打开同一份 <account>.session,而旧进程若还活着就是两个写者。
    # expected=proc：等待期间可能有并发 start() 抢先登记了新子进程，不能误删。
    _forget(key, expected=proc)
    return True, f"账号 {account} 的 {kind} 任务已停止"


def shutdown_all(timeout: float = 5.0) -> List[str]:
    """Terminate all tracked child processes and release their locks.

    Intended to be called from a WebUI shutdown hook so that children do
    not become orphans when the WebUI process exits. Returns the list of
    stopped process keys.
    """
    stopped: List[str] = []
    with _STATE_LOCK:
        snapshot = list(_PROCESSES.items())
    for key, proc in snapshot:
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
        _forget(key, expected=proc)
        stopped.append(key)
    return stopped
