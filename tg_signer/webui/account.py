"""Account login/logout helpers for the WebUI (kept free of NiceGUI imports)."""

import asyncio
import json
import os
import pathlib
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from pyrogram import errors

from tg_signer import core as tg_core
from tg_signer.core import (
    Client,
    chat_to_dict,
    get_api_config,
    get_client,
    get_proxy,
    write_latest_chats,
)
from tg_signer.utils import resolve_under

# 每账号一个登录会话,会话内持有一个 daemon 线程 + 独立 event loop + 一个
# Client。用户 send_code 之后中途放弃(关页面 / 不发验证码)时这些资源没人回收,
# 所以给会话加 TTL,由下一次调用顺手淘汰。
LOGIN_SESSION_TTL_SECONDS = 10 * 60
# LOGIN_SESSIONS 由 FastAPI 线程池并发读写(每个请求一个线程),所有访问都要过锁。
_LOGIN_SESSIONS_LOCK = threading.Lock()
LOGIN_SESSIONS: Dict[str, "_AccountLoginSession"] = {}
_ACCOUNT_USERS_FILE = "webui_accounts.json"
# 登录在各自的线程里并发进行，映射文件的读-改-写必须串行，否则互相覆盖。
_ACCOUNT_USERS_LOCK = threading.Lock()
# 每个账号一把锁，用来把「关旧会话 -> 建新会话 -> 登记」这段串行化。
# 不能直接用 _LOGIN_SESSIONS_LOCK：close() 和会话构造都是慢操作（前者要 join
# 线程，最多 5s），持有全局锁会连累所有其它账号的登录与 TTL 回收。
_LOGIN_LOCKS: Dict[str, threading.Lock] = {}


def _account_login_lock(account: str) -> threading.Lock:
    with _LOGIN_SESSIONS_LOCK:
        lock = _LOGIN_LOCKS.get(account)
        if lock is None:
            lock = threading.Lock()
            _LOGIN_LOCKS[account] = lock
        return lock


def _account_path(account: str, workdir, suffix: str = "") -> pathlib.Path:
    """返回 ``<workdir>/<account><suffix>``,账号名越界时抛 ``ValueError``。

    账号名来自请求体并会被拼进 session 文件名;注销流程还会 ``unlink()``,
    所以必须保证它是 ``workdir`` 下的单一路径分量。
    """
    return resolve_under(pathlib.Path(workdir), account, suffix=suffix)


def list_accounts(workdir) -> List[Dict[str, Any]]:
    """Scan workdir for session files and return account summaries."""
    workdir = pathlib.Path(workdir)
    accounts: Dict[str, Dict[str, Any]] = {}
    for suffix, kind in (
        (".session", "session"),
        (".session_string", "session_string"),
    ):
        for session_file in workdir.glob(f"*{suffix}"):
            name = session_file.name[: -len(suffix)]
            entry = accounts.setdefault(
                name, {"account": name, "kind": [], "session_file": None}
            )
            if kind not in entry["kind"]:
                entry["kind"].append(kind)
            if suffix == ".session":
                entry["session_file"] = str(session_file)
    result = []
    for entry in accounts.values():
        entry["kind"] = sorted(entry["kind"])
        result.append(entry)
    return sorted(result, key=lambda item: item["account"].lower())


def load_account_users(workdir) -> Dict[str, str]:
    """Return the account->user_id mapping written by WebUI logins."""
    workdir = pathlib.Path(workdir)
    mapping_file = workdir / _ACCOUNT_USERS_FILE
    if not mapping_file.is_file():
        return {}
    try:
        data = json.loads(mapping_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def _update_account_users(workdir: pathlib.Path, mutate) -> None:
    """在锁内完成「读 -> 改 -> 原子写」，并把 load 与 save 之间做成临界区。

    登录在各自的线程里跑，两个账号同时登录完成时会并发进入
    ``save_account_user``：都读到同一份旧映射，各自追加一条再整份写回，
    后写者把前者的条目整段覆盖掉（实测并发登录只剩最后一个账号）。
    写文件也改成「临时文件 + os.replace」，否则进程中途被杀会留下半个 JSON，
    下次 load 直接当损坏处理、映射整体丢失。
    """
    workdir.mkdir(parents=True, exist_ok=True)
    mapping_file = workdir / _ACCOUNT_USERS_FILE
    with _ACCOUNT_USERS_LOCK:
        data = load_account_users(workdir)
        result = mutate(data)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        tmp = mapping_file.with_suffix(mapping_file.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, mapping_file)
        return result


def save_account_user(account: str, user_id: Any, workdir) -> None:
    """Record the WebUI-created account->user_id mapping."""
    _update_account_users(
        pathlib.Path(workdir), lambda data: data.__setitem__(account, str(user_id))
    )


def remove_account_user(account: str, workdir) -> None:
    """Delete the cached users/<user_id> directory recorded for the account."""
    workdir = pathlib.Path(workdir)

    def _mutate(data):
        user_id = data.pop(account, None)
        if user_id is not None and str(user_id).isdigit():
            user_dir = workdir / "users" / str(user_id)
            if user_dir.is_dir():
                shutil.rmtree(user_dir, ignore_errors=True)
        return user_id

    _update_account_users(workdir, _mutate)


class _AccountLoginSession:
    def __init__(self, account: str, workdir: pathlib.Path):
        self.account = account
        self.workdir = pathlib.Path(workdir)
        # 下面的 get_client 会把账号名拼进 session 文件路径,先校验一次。
        _account_path(account, self.workdir)
        self.created_at = time.monotonic()
        self.phone = ""
        self.phone_code_hash: Optional[str] = None
        self.loop = asyncio.new_event_loop()
        # 线程排在 get_client 之后再启动：get_client() 可能抛（session 文件不可用、
        # 参数非法），而在它之前就 run_forever 的话，每次失败的登录尝试都会留下
        # 一个仍在跑的线程和一个未关闭的 event loop，反复登录就持续堆积。
        self.thread = threading.Thread(
            target=self.loop.run_forever,
            daemon=True,
            name=f"webui-login-{account}",
        )
        self.client = get_client(
            account, get_proxy(), workdir=str(self.workdir), loop=self.loop
        )
        self.thread.start()

    def run(self, coro, timeout: float):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    async def _send_code(self, phone: str) -> Tuple[str, str]:
        await self.client.connect()
        try:
            me = await self.client.get_me()
        except Exception:  # noqa: BLE001
            me = None
        if me is not None:
            name = me.first_name or me.username or me.id
            return "already", f"该账号已登录: {name}"
        sent = await self.client.send_code(phone)
        self.phone = phone
        self.phone_code_hash = sent.phone_code_hash
        return "ok", "验证码已发送，请查收 Telegram"

    def send_code(self, phone: str, timeout: float = 90.0) -> Tuple[str, str]:
        try:
            return self.run(self._send_code(phone), timeout)
        except Exception as exc:  # noqa: BLE001
            return "error", str(exc)

    async def _complete(self, code: str, password: Optional[str]) -> Tuple[str, str]:
        try:
            try:
                await self.client.sign_in(self.phone, self.phone_code_hash, code)
            except errors.SessionPasswordNeeded:
                if not password:
                    return "password_needed", "需要两步验证密码"
                await self.client.check_password(password)
        except Exception as exc:  # noqa: BLE001
            return "error", str(exc)

        try:
            me = await self.client.get_me()
            user_dir = self.workdir / "users" / str(me.id)
            user_dir.mkdir(parents=True, exist_ok=True)
            (user_dir / "me.json").write_text(str(me), encoding="utf-8")
            save_account_user(self.account, me.id, self.workdir)
            try:
                await self.client.save_session_string()
            except Exception:  # noqa: BLE001
                pass
            try:
                latest_chats = []
                async for dialog in self.client.get_dialogs(limit=20):
                    latest_chats.append(chat_to_dict(dialog.chat))
                write_latest_chats(user_dir / "latest_chats.json", latest_chats)
            except Exception as exc:  # noqa: BLE001
                return "ok", f"登录成功，但获取最近对话失败: {exc}"
        except Exception as exc:  # noqa: BLE001
            return "error", str(exc)
        return "ok", f"登录成功: {me.first_name or me.username or me.id}"

    def complete(self, code: str, password: Optional[str]) -> Tuple[str, str]:
        try:
            return self.run(self._complete(code, password), 120.0)
        except Exception as exc:  # noqa: BLE001
            return "error", str(exc)

    def close(self) -> None:
        # 先从注册表摘掉自己(加锁),再做阻塞式的线程 / loop 收尾(不加锁:
        # 这里可能要等 5 秒,不该把整张注册表锁住)。
        with _LOGIN_SESSIONS_LOCK:
            if LOGIN_SESSIONS.get(self.account) is self:
                LOGIN_SESSIONS.pop(self.account, None)
        # 彻底停掉 client 并清 core 缓存,避免下次同账号登录时拿到绑定旧 loop 的 client
        try:
            if self.thread.is_alive():
                try:
                    self.run(self._close_client(), timeout=5)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            try:
                # 走 core 的唯一回收入口，不再直接戳它的私有容器。
                tg_core.forget_client(self.client.key)
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.thread.join(timeout=5)
                # loop 也要 close：每个登录会话都新建一个，反复登录/重登会持续
                # 泄漏未关闭的 event loop（Windows 上还各占一个 select 句柄）。
                if not self.loop.is_closed():
                    self.loop.close()
            except Exception:  # noqa: BLE001
                pass

    async def _close_client(self) -> None:
        try:
            if self.client.is_connected:
                await self.client.stop()
        except Exception:  # noqa: BLE001
            pass


def prune_login_sessions() -> List[str]:
    """关闭并移除超过 TTL 的登录会话,返回被回收的账号名。

    回收动作(关闭 client / 停线程)会阻塞,所以先加锁把过期条目从注册表摘出来,
    再在锁外逐个 ``close()``;``close()`` 自己也会去摘注册表,此处要保证幂等。
    """
    now = time.monotonic()
    with _LOGIN_SESSIONS_LOCK:
        expired = [
            account
            for account, session in LOGIN_SESSIONS.items()
            if now - session.created_at > LOGIN_SESSION_TTL_SECONDS
        ]
        sessions = [LOGIN_SESSIONS.pop(account, None) for account in expired]
    closed: List[str] = []
    for account, session in zip(expired, sessions, strict=True):
        if session is not None:
            session.close()
            closed.append(account)
    return closed


def close_all_login_sessions() -> List[str]:
    """关闭并移除**全部**登录会话,返回被回收的账号名。

    与 :func:`prune_login_sessions` 的区别在于不看 TTL。切换工作目录时必须用
    这个:登录会话在构造时就固定了 workdir（``_AccountLoginSession.__init__``）,
    而「发验证码 → 切目录 → 粘贴验证码」这条最常见的路径里,会话只有几秒大,
    远未到 TTL。原实现只调用 prune,于是会话活过切换,随后 complete-login 把
    .session / users/<id>/ 缓存 / webui_accounts.json 全部写进**刚切走的旧目录**,
    并如实返回「登录成功」—— 而当前目录里这个账号根本不存在,用户也无从找回。
    """
    with _LOGIN_SESSIONS_LOCK:
        accounts = list(LOGIN_SESSIONS)
        sessions = list(LOGIN_SESSIONS.values())
        LOGIN_SESSIONS.clear()
    # close() 在锁外做阻塞收尾；它内部会再进 _LOGIN_SESSIONS_LOCK 摘自己，
    # 而此时注册表已空，`if LOGIN_SESSIONS.get(...) is self` 不成立，天然幂等。
    for session in sessions:
        try:
            session.close()
        except Exception:  # noqa: BLE001
            pass
    return accounts


def send_login_code(account: str, phone: str, workdir) -> Tuple[str, str]:
    prune_login_sessions()
    # 整段「关旧会话 -> 建新会话 -> 登记」必须按账号串行。
    # 原来「弹出旧会话」和「登记新会话」是两次独立的加锁，中间还夹着两次慢操作
    # (close() 要 join 线程、构造要起线程)。两个并发请求(重复点「发送验证码」)
    # 会各自建一个会话,后登记的直接覆盖先登记的 —— 先登记的那个既离开了
    # LOGIN_SESSIONS 又不会被 close(),线程 / event loop / Telegram 连接三重泄漏,
    # 而用户拿到的是第二个验证码,用第一个必然失败。
    with _account_login_lock(account):
        with _LOGIN_SESSIONS_LOCK:
            existing = LOGIN_SESSIONS.pop(account, None)
        if existing is not None:
            existing.close()
        session = _AccountLoginSession(account, pathlib.Path(workdir))
        try:
            with _LOGIN_SESSIONS_LOCK:
                LOGIN_SESSIONS[account] = session
        except Exception:  # noqa: BLE001
            # 登记不上就不能让它变成孤儿。
            session.close()
            raise
        return session.send_code(phone)


def complete_login(
    account: str, code: str, password: Optional[str] = None
) -> Tuple[str, str]:
    prune_login_sessions()
    with _LOGIN_SESSIONS_LOCK:
        session = LOGIN_SESSIONS.get(account)
    if session is None:
        return "error", "登录会话不存在，请重新发起登录"
    status, message = session.complete(code, password)
    if status == "ok":
        session.close()
    return status, message


def _new_client(account: str, workdir: pathlib.Path) -> Any:
    """Create a standalone Client for an existing account session.

    Prefers a file-backed ``<account>.session`` when present; falls back to an
    in-memory client backed by ``<account>.session_string`` so that
    session_string-only accounts also work in the WebUI flows.

    Does not pass loop – Pyrogram resolves the running loop via
    asyncio.get_event_loop() automatically.  This avoids cross-loop
    bugs when called from asyncio.to_thread or nested loops.
    """
    workdir = pathlib.Path(workdir)
    api_id, api_hash = get_api_config()
    session_file = _account_path(account, workdir, ".session")
    session_string_file = _account_path(account, workdir, ".session_string")
    in_memory = not session_file.is_file() and session_string_file.is_file()
    return Client(
        account,
        api_id=api_id,
        api_hash=api_hash,
        proxy=get_proxy(),
        workdir=str(workdir),
        in_memory=in_memory,
        key=str(_account_path(account, workdir).resolve()),
    )


def _session_file_usable(account: str, workdir: pathlib.Path) -> bool:
    """本地判断账号是否有可复用的 session 文件,不触碰 SQLite,不发起连接。

    检查两种持久化形态之一即可:pyrogram 的 ``<account>.session``(SQLite)
    或 in-memory 的 ``<account>.session_string``。文件存在且非空即视为可用。

    为什么不做 ``client.connect()``:connect 会打开同一个 SQLite session 文件,
    若后台已有同账号任务子进程在用,会触发 ``database is locked``;且「校验」
    不应等于「重连」——真实连接由任务子进程负责。
    """
    workdir = pathlib.Path(workdir)
    for suffix in (".session", ".session_string"):
        f = _account_path(account, workdir, suffix)
        try:
            if f.is_file() and f.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


async def is_account_authorized(account: str, workdir) -> Tuple[bool, str]:
    """账号是否有可复用的本地 session(纯文件检查,不连接 Telegram)。

    语义(按用户要求,2026-09-13):session 文件存在且可用即视为已授权,
    不再新建 Client 去 connect —— 避免与后台任务子进程争用同一 SQLite
    session 文件触发 ``database is locked``。
    """
    if _session_file_usable(account, workdir):
        return True, f"{account} session 有效"
    return False, f"{account} 未登录或 session 无效，请先在“账号管理”登录"


async def fetch_dialogs(
    account: str, workdir, limit: int = 50
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """通过指定账号实时获取最近对话，不写入本地缓存。"""
    workdir = pathlib.Path(workdir)
    client = _new_client(account, workdir)
    chats: List[Dict[str, Any]] = []
    try:
        authorized = await client.connect()
        if not authorized:
            return (
                False,
                f"{account} 未登录或 session 无效，请先在“账号管理”登录",
                chats,
            )
        me = await client.get_me()
        async for dialog in client.get_dialogs(limit=limit):
            chats.append(chat_to_dict(dialog.chat))
    except Exception as exc:  # noqa: BLE001
        return False, f"获取最近对话失败: {exc}", chats
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    name = me.first_name or me.username or me.id
    return True, f"已获取最近 {len(chats)} 个对话: {name}", chats


async def logout_account(account: str, workdir) -> str:
    """Log out from Telegram and delete local session files."""
    workdir = pathlib.Path(workdir)
    if not _session_file_usable(account, workdir):
        # 账号连本地 session 都没有：不存在可登出的登录态。旧实现照样
        # _new_client(...).connect()，为一个不存在的账号发起真实 Telegram 连接
        # —— 既是无意义的外联，也会在无网络时把请求拖到超时。
        return f"{account} 未登录或 session 不存在，无需登出"
    client = _new_client(account, workdir)
    failed: Optional[str] = None
    try:
        is_authorized = await client.connect()
        if is_authorized:
            await client.log_out()
        else:
            await client.storage.delete()
    except Exception as exc:  # noqa: BLE001
        failed = str(exc)
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    # 本地清理放在异常处理之后，而不是 finally：
    # Telegram 侧登出失败（FloodWait / 断网 / session 被吊销）时，API 会如实
    # 返回失败，而清理动作此前在 finally 里无条件执行 —— 用户看到「登出失败」
    # 却发现 session 文件和 users/<id> 缓存已被删光，且没有任何途径撤销。
    if failed is not None:
        raise RuntimeError(f"登出失败: {failed}")
    remove_account_user(account, workdir)
    # Windows 上 <account>.session 是 SQLite 文件，可能仍被子进程占用，
    # unlink() 会抛 PermissionError（OSError 不在 server 的 400 捕获集合里，
    # 会变成 500 + traceback）。
    failures: List[str] = []
    for suffix in (".session", ".session-journal", ".session_string"):
        session_file = _account_path(account, workdir, suffix)
        try:
            if session_file.is_file():
                session_file.unlink()
        except OSError as exc:
            failures.append(f"{session_file.name}: {exc}")
    if failures:
        raise RuntimeError(
            f"{account} 已在 Telegram 侧登出，但本地 session 文件删除失败（文件可能"
            f"仍被任务进程占用）：" + "；".join(failures)
        )
    return f"已登出并删除 session 文件: {account}"
