import importlib.util
from pathlib import Path

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
