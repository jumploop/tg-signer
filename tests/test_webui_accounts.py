import importlib.util
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


def test_save_and_remove_account_user_mapping(tmp_path):
    account.save_account_user("acc1", "123", tmp_path)
    assert account.load_account_users(tmp_path) == {"acc1": "123"}

    user_dir = tmp_path / "users" / "123"
    user_dir.mkdir(parents=True)
    (user_dir / "me.json").write_text("x", encoding="utf-8")

    account.remove_account_user("acc1", tmp_path)
    assert account.load_account_users(tmp_path) == {}
    assert not user_dir.exists()
