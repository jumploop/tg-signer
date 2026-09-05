"""Account login/logout helpers for the WebUI (kept free of NiceGUI imports)."""

import asyncio
import json
import pathlib
import threading
from typing import Any, Dict, List, Optional, Tuple

from pyrogram import errors

from tg_signer.core import Client, get_api_config, get_client, get_proxy

LOGIN_SESSIONS: Dict[str, "_AccountLoginSession"] = {}


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

    async def _send_code(self, phone: str) -> None:
        await self.client.connect()
        sent = await self.client.send_code(phone)
        self.phone = phone
        self.phone_code_hash = sent.phone_code_hash

    def send_code(self, phone: str, timeout: float = 90.0) -> Tuple[str, str]:
        try:
            self.run(self._send_code(phone), timeout)
        except Exception as exc:  # noqa: BLE001
            return "error", str(exc)
        return "ok", "验证码已发送，请查收 Telegram"

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
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=5)
        finally:
            LOGIN_SESSIONS.pop(self.account, None)


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


def cancel_login(account: str) -> None:
    session = LOGIN_SESSIONS.pop(account, None)
    if session is not None:
        session.close()


def logout_account(account: str, workdir) -> str:
    """Log out from Telegram and delete local session files."""
    workdir = pathlib.Path(workdir)
    loop = asyncio.new_event_loop()
    proxy = get_proxy()
    api_id, api_hash = get_api_config()
    client = Client(
        account,
        api_id=api_id,
        api_hash=api_hash,
        proxy=proxy,
        workdir=str(workdir),
        loop=loop,
        key=str((workdir / account).resolve()),
    )
    try:
        is_authorized = loop.run_until_complete(client.connect())
        if is_authorized:
            loop.run_until_complete(client.log_out())
        else:
            loop.run_until_complete(client.storage.delete())
    except Exception as exc:  # noqa: BLE001
        # Best-effort: remove local session files even if the remote call fails.
        loop.run_until_complete(client.storage.delete())
        raise RuntimeError(f"登出失败: {exc}") from exc
    finally:
        loop.close()
        for suffix in (".session", ".session-journal", ".session_string"):
            session_file = workdir / f"{account}{suffix}"
            if session_file.is_file():
                session_file.unlink()
    return f"已登出并删除 session 文件: {account}"
