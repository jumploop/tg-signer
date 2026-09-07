"""Account login/logout helpers for the WebUI (kept free of NiceGUI imports)."""

import asyncio
import json
import pathlib
import shutil
import threading
from typing import Any, Dict, List, Optional, Tuple

from pyrogram import errors

from tg_signer import core as tg_core
from tg_signer.core import Client, get_api_config, get_client, get_proxy

LOGIN_SESSIONS: Dict[str, "_AccountLoginSession"] = {}
_ACCOUNT_USERS_FILE = "webui_accounts.json"


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


def save_account_user(account: str, user_id: Any, workdir) -> None:
    """Record the WebUI-created account->user_id mapping."""
    workdir = pathlib.Path(workdir)
    data = load_account_users(workdir)
    data[account] = str(user_id)
    workdir.mkdir(parents=True, exist_ok=True)
    mapping_file = workdir / _ACCOUNT_USERS_FILE
    mapping_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def remove_account_user(account: str, workdir) -> None:
    """Delete the cached users/<user_id> directory recorded for the account."""
    workdir = pathlib.Path(workdir)
    data = load_account_users(workdir)
    user_id = data.pop(account, None)
    if user_id is not None and str(user_id).isdigit():
        user_dir = workdir / "users" / str(user_id)
        if user_dir.is_dir():
            shutil.rmtree(user_dir, ignore_errors=True)
        mapping_file = workdir / _ACCOUNT_USERS_FILE
        mapping_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class _AccountLoginSession:
    def __init__(self, account: str, workdir: pathlib.Path):
        self.account = account
        self.workdir = pathlib.Path(workdir)
        self.phone = ""
        self.phone_code_hash: Optional[str] = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self.loop.run_forever,
            daemon=True,
            name=f"webui-login-{account}",
        )
        self.thread.start()
        self.client = get_client(
            account, get_proxy(), workdir=str(self.workdir), loop=self.loop
        )

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
                    latest_chats.append(
                        {
                            "id": dialog.chat.id,
                            "title": dialog.chat.title,
                            "type": dialog.chat.type,
                            "username": dialog.chat.username,
                            "first_name": dialog.chat.first_name,
                            "last_name": dialog.chat.last_name,
                        }
                    )
                with open(user_dir / "latest_chats.json", "w", encoding="utf-8") as fp:
                    json.dump(
                        latest_chats,
                        fp,
                        ensure_ascii=False,
                        indent=4,
                        default=lambda o: getattr(o, "value", str(o)),
                    )
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
        # 彻底停掉 client 并清 core 缓存,避免下次同账号登录时拿到绑定旧 loop 的 client
        try:
            if self.thread.is_alive():
                try:
                    self.run(self._close_client(), timeout=5)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            try:
                tg_core._CLIENT_INSTANCES.pop(self.client.key, None)
                tg_core._CLIENT_REFS.pop(self.client.key, None)
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.thread.join(timeout=5)
            except Exception:  # noqa: BLE001
                pass
            LOGIN_SESSIONS.pop(self.account, None)

    async def _close_client(self) -> None:
        try:
            if self.client.is_connected:
                await self.client.stop()
        except Exception:  # noqa: BLE001
            pass


def send_login_code(account: str, phone: str, workdir) -> Tuple[str, str]:
    existing = LOGIN_SESSIONS.get(account)
    if existing is not None:
        existing.close()
    session = _AccountLoginSession(account, pathlib.Path(workdir))
    LOGIN_SESSIONS[account] = session
    return session.send_code(phone)


def complete_login(
    account: str, code: str, password: Optional[str] = None
) -> Tuple[str, str]:
    session = LOGIN_SESSIONS.get(account)
    if session is None:
        return "error", "登录会话不存在，请重新发起登录"
    status, message = session.complete(code, password)
    if status == "ok":
        session.close()
    return status, message


def _new_client(account: str, workdir: pathlib.Path) -> Any:
    """Create a standalone Client for an existing <account>.session file.

    Does not pass loop – Pyrogram resolves the running loop via
    asyncio.get_event_loop() automatically.  This avoids cross-loop
    bugs when called from asyncio.to_thread or nested loops.
    """
    api_id, api_hash = get_api_config()
    return Client(
        account,
        api_id=api_id,
        api_hash=api_hash,
        proxy=get_proxy(),
        workdir=str(workdir),
        key=str((workdir / account).resolve()),
    )


async def is_account_authorized(account: str, workdir) -> Tuple[bool, str]:
    """Check whether the account's session file can connect to Telegram."""
    workdir = pathlib.Path(workdir)
    client = _new_client(account, workdir)
    try:
        authorized = await client.connect()
        if not authorized:
            return False, f"{account} 未登录或 session 无效，请先在“账号管理”登录"
    except Exception as exc:  # noqa: BLE001
        return False, f"{account} 校验失败: {exc}"
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    return True, f"{account} session 有效"


async def refresh_dialogs(account: str, workdir, limit: int = 50) -> Tuple[bool, str]:
    """Reuse an existing session to refresh the latest dialogs cache.

    Writes users/<me.id>/latest_chats.json (and me.json) inside workdir so the
    group config page can list freshly fetched chats.
    """
    workdir = pathlib.Path(workdir)
    client = _new_client(account, workdir)
    try:
        authorized = await client.connect()
        if not authorized:
            return False, f"{account} 未登录或 session 无效，请先在“账号管理”登录"
        me = await client.get_me()
        user_dir = workdir / "users" / str(me.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "me.json").write_text(str(me), encoding="utf-8")
        save_account_user(account, me.id, workdir)

        chats: List[Dict[str, Any]] = []

        async def _fetch_dialogs() -> None:
            async for dialog in client.get_dialogs(limit=limit):
                chats.append(
                    {
                        "id": dialog.chat.id,
                        "title": dialog.chat.title,
                        "type": dialog.chat.type,
                        "username": dialog.chat.username,
                        "first_name": dialog.chat.first_name,
                        "last_name": dialog.chat.last_name,
                    }
                )

        await _fetch_dialogs()
        (user_dir / "latest_chats.json").write_text(
            json.dumps(
                chats,
                ensure_ascii=False,
                indent=4,
                default=lambda o: getattr(o, "value", str(o)),
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"刷新最近对话失败: {exc}"
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    name = me.first_name or me.username or me.id
    return True, f"已刷新最近 {len(chats)} 个对话: {name}"


def cancel_login(account: str) -> None:
    session = LOGIN_SESSIONS.pop(account, None)
    if session is not None:
        session.close()


async def logout_account(account: str, workdir) -> str:
    """Log out from Telegram and delete local session files."""
    workdir = pathlib.Path(workdir)
    client = _new_client(account, workdir)
    try:
        is_authorized = await client.connect()
        if is_authorized:
            await client.log_out()
        else:
            await client.storage.delete()
    except Exception as exc:  # noqa: BLE001
        try:
            await client.storage.delete()
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"登出失败: {exc}") from exc
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        remove_account_user(account, workdir)
        for suffix in (".session", ".session-journal", ".session_string"):
            session_file = workdir / f"{account}{suffix}"
            if session_file.is_file():
                session_file.unlink()
    return f"已登出并删除 session 文件: {account}"
