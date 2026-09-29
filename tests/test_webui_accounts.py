import importlib.util
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_ACCOUNT_PATH = (
    Path(__file__).resolve().parents[1] / "tg_signer" / "webui" / "account.py"
)
_spec = importlib.util.spec_from_file_location("tg_signer_webui_account", _ACCOUNT_PATH)
account = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(account)


def test_list_accounts_empty(tmp_path):
    assert account.list_accounts(tmp_path) == []


def test_list_accounts_detects_session_files(tmp_path):
    (tmp_path / "my_account.session").write_text("x", encoding="utf-8")
    (tmp_path / "my_account.session_journal").write_text("x", encoding="utf-8")
    (tmp_path / "other.session_string").write_text("x", encoding="utf-8")

    accounts = account.list_accounts(tmp_path)
    assert [item["account"] for item in accounts] == ["my_account", "other"]

    by_name = {item["account"]: item for item in accounts}
    assert by_name["my_account"]["session_file"] is not None
    assert "session" in by_name["my_account"]["kind"]
    assert "session_string" in by_name["other"]["kind"]


def test_list_accounts_ignores_other_files(tmp_path):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert account.list_accounts(tmp_path) == []


def test_session_file_usable(tmp_path):
    assert not account._session_file_usable("acc", tmp_path)

    (tmp_path / "acc.session").write_text("x", encoding="utf-8")
    assert account._session_file_usable("acc", tmp_path)

    (tmp_path / "acc.session").write_text("", encoding="utf-8")
    assert not account._session_file_usable("acc", tmp_path)

    (tmp_path / "acc.session").unlink()
    (tmp_path / "acc.session_string").write_text("x", encoding="utf-8")
    assert account._session_file_usable("acc", tmp_path)


@pytest.mark.asyncio
async def test_is_account_authorized_checks_local_session_files(tmp_path):
    ok, msg = await account.is_account_authorized("acc", tmp_path)
    assert not ok
    assert "登录" in msg

    (tmp_path / "acc.session").write_text("x", encoding="utf-8")
    ok, msg = await account.is_account_authorized("acc", tmp_path)
    assert ok
    assert "session 有效" in msg


@pytest.mark.asyncio
async def test_fetch_dialogs_returns_live_dialogs_without_writing_cache(
    monkeypatch, tmp_path
):
    class FakeClient:
        is_connected = True

        async def connect(self):
            return True

        async def get_me(self):
            return SimpleNamespace(id=123, first_name="测试账号", username=None)

        async def get_dialogs(self, limit):
            assert limit == 50
            yield SimpleNamespace(
                chat=SimpleNamespace(
                    id=-1001,
                    title="测试频道",
                    type="channel",
                    username="test_channel",
                    first_name=None,
                    last_name=None,
                )
            )

        async def disconnect(self):
            self.is_connected = False

    monkeypatch.setattr(account, "_new_client", lambda *_args: FakeClient())

    ok, message, chats = await account.fetch_dialogs("acc", tmp_path)

    assert ok
    assert "已获取最近 1 个对话" in message
    assert chats == [
        {
            "id": -1001,
            "title": "测试频道",
            "type": "channel",
            "username": "test_channel",
            "first_name": None,
            "last_name": None,
        }
    ]
    assert not (tmp_path / "users" / "123" / "latest_chats.json").exists()


def test_new_client_uses_in_memory_for_session_string_only(tmp_path):
    (tmp_path / "acc.session_string").write_text("dummy-string", encoding="utf-8")
    client = account._new_client("acc", tmp_path)
    assert client.in_memory is True
    assert client.session_string == "dummy-string"


def test_new_client_prefers_session_file(tmp_path):
    (tmp_path / "acc.session").write_bytes(b"x")
    (tmp_path / "acc.session_string").write_text("dummy", encoding="utf-8")
    client = account._new_client("acc", tmp_path)
    assert client.in_memory is False


@pytest.mark.asyncio
async def test_logout_account_removes_files_for_session_string_only(
    monkeypatch, tmp_path
):
    class FakeStorage:
        async def delete(self):
            return None

    class FakeClient:
        is_connected = False
        storage = FakeStorage()

        async def connect(self):
            return False

        async def disconnect(self):
            self.is_connected = False

        async def log_out(self):
            return None

    monkeypatch.setattr(account, "_new_client", lambda *_args: FakeClient())
    (tmp_path / "acc.session_string").write_text("x", encoding="utf-8")

    msg = await account.logout_account("acc", tmp_path)

    assert "已登出" in msg
    assert not (tmp_path / "acc.session_string").exists()


def test_save_and_remove_account_user_mapping(tmp_path):
    account.save_account_user("acc1", "123", tmp_path)
    assert account.load_account_users(tmp_path) == {"acc1": "123"}

    user_dir = tmp_path / "users" / "123"
    user_dir.mkdir(parents=True)
    (user_dir / "me.json").write_text("x", encoding="utf-8")

    account.remove_account_user("acc1", tmp_path)
    assert account.load_account_users(tmp_path) == {}
    assert not user_dir.exists()


# ---------------------------------------------------------------------------
# 登录会话注册表：TTL 回收 + 并发安全
#
# 登录会话持有 daemon 线程 + 独立 event loop + 一个 Client。用户在 send_code
# 之后直接关掉页面时没人回收，所以给会话加 TTL；注册表又被 FastAPI 线程池
# 并发读写，所以所有访问必须过锁。
# ---------------------------------------------------------------------------


class _FakeLoginSession:
    """最小登录会话替身：只需要 ``created_at`` 与 ``close()``。"""

    def __init__(self, name, age=0.0):
        self.account = name
        self.created_at = time.monotonic() - age
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        # 与真实实现一致：只有当注册表里还是自己时才摘除（幂等）。
        with account._LOGIN_SESSIONS_LOCK:
            if account.LOGIN_SESSIONS.get(self.account) is self:
                account.LOGIN_SESSIONS.pop(self.account, None)


@pytest.fixture()
def clean_login_sessions():
    """登录会话注册表是模块级全局状态，用例前后都要清干净。"""
    with account._LOGIN_SESSIONS_LOCK:
        account.LOGIN_SESSIONS.clear()
    yield
    with account._LOGIN_SESSIONS_LOCK:
        account.LOGIN_SESSIONS.clear()


def test_prune_login_sessions_reaps_only_expired(clean_login_sessions):
    fresh = _FakeLoginSession("fresh")
    stale = _FakeLoginSession("stale", age=account.LOGIN_SESSION_TTL_SECONDS + 1)
    with account._LOGIN_SESSIONS_LOCK:
        account.LOGIN_SESSIONS.update({"fresh": fresh, "stale": stale})

    assert account.prune_login_sessions() == ["stale"]
    assert stale.close_calls == 1
    assert fresh.close_calls == 0
    with account._LOGIN_SESSIONS_LOCK:
        assert set(account.LOGIN_SESSIONS) == {"fresh"}


def test_send_login_code_prunes_expired_sessions_first(
    clean_login_sessions, monkeypatch, tmp_path
):
    """发起新登录时应顺带回收别账号的过期会话，而不是无限堆积线程。"""
    stale = _FakeLoginSession("old", age=account.LOGIN_SESSION_TTL_SECONDS + 1)
    with account._LOGIN_SESSIONS_LOCK:
        account.LOGIN_SESSIONS["old"] = stale

    created = []

    class _FakeNewSession:
        def __init__(self, name, workdir):
            created.append((name, Path(workdir)))
            self.account = name

        def send_code(self, phone):
            return "ok", f"验证码已发送至 {phone}"

    monkeypatch.setattr(account, "_AccountLoginSession", _FakeNewSession)

    assert account.send_login_code("acc", "+10086", tmp_path) == (
        "ok",
        "验证码已发送至 +10086",
    )
    assert stale.close_calls == 1
    assert created == [("acc", Path(tmp_path))]
    with account._LOGIN_SESSIONS_LOCK:
        assert set(account.LOGIN_SESSIONS) == {"acc"}


def test_send_login_code_closes_replaced_session(
    clean_login_sessions, monkeypatch, tmp_path
):
    """同账号重复发起登录：旧会话必须被关闭，否则线程与 client 泄漏。"""
    old = _FakeLoginSession("acc")
    with account._LOGIN_SESSIONS_LOCK:
        account.LOGIN_SESSIONS["acc"] = old

    class _FakeNewSession:
        def __init__(self, name, workdir):
            self.account = name

        def send_code(self, phone):
            return "ok", "sent"

    monkeypatch.setattr(account, "_AccountLoginSession", _FakeNewSession)

    assert account.send_login_code("acc", "+1", tmp_path)[0] == "ok"
    assert old.close_calls == 1
    with account._LOGIN_SESSIONS_LOCK:
        assert account.LOGIN_SESSIONS["acc"] is not old


def test_complete_login_without_session_reports_restart(clean_login_sessions):
    assert account.complete_login("acc", "12345") == (
        "error",
        "登录会话不存在，请重新发起登录",
    )


def test_login_session_close_is_idempotent_and_spares_newer_session(
    clean_login_sessions, tmp_path
):
    """``close()`` 必须先摘除自己再收尾，且不得误摘同账号的新会话。"""
    session = account._AccountLoginSession("acc", tmp_path)
    try:
        with account._LOGIN_SESSIONS_LOCK:
            account.LOGIN_SESSIONS["acc"] = session

        session.close()
        with account._LOGIN_SESSIONS_LOCK:
            assert "acc" not in account.LOGIN_SESSIONS

        # 重复关闭必须幂等（收尾逻辑在 finally 里，loop 已经停了）。
        session.close()

        newer = _FakeLoginSession("acc")
        with account._LOGIN_SESSIONS_LOCK:
            account.LOGIN_SESSIONS["acc"] = newer
        session.close()
        with account._LOGIN_SESSIONS_LOCK:
            assert account.LOGIN_SESSIONS.get("acc") is newer
    finally:
        with account._LOGIN_SESSIONS_LOCK:
            account.LOGIN_SESSIONS.pop("acc", None)
