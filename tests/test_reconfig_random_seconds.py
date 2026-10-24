"""交互式配置的时间误差必须是可重问的非负整数。

历史问题：``ask_for_config`` 直接 ``int(float(input()))`` 后交给
``SignConfigV3.model_validate``，输入 ``-5`` 会在 pydantic 里抛
ValidationError，整个 ``tg-signer reconfig`` 以裸 traceback 退出。
"""

import pytest

from tg_signer.core import UserSigner


def _signer(tmp_path) -> UserSigner:
    return UserSigner(task_name="task", account="acct", session_dir=tmp_path)


def _make_signer_with_chat(tmp_path):
    from tg_signer.config import SignChatV3

    signer = _signer(tmp_path)
    signer._dummy_chat = SignChatV3.model_validate(
        {"chat_id": 1, "name": "c", "actions": [{"text": "hi"}]}
    )
    return signer


def test_negative_random_seconds_is_reasked(monkeypatch, tmp_path):
    signer = _make_signer_with_chat(tmp_path)
    # ask_one → 继续配置?(n) → sign_at(默认) → random_seconds(-5) → random_seconds(30)
    inputs = iter(["n", "", "-5", "30"])
    monkeypatch.setattr(UserSigner, "ask_one", lambda self: self._dummy_chat)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    config = signer.ask_for_config()

    assert config.random_seconds == 30


def test_non_numeric_random_seconds_is_reasked(monkeypatch, tmp_path):
    signer = _make_signer_with_chat(tmp_path)
    inputs = iter(["n", "", "abc", "inf", "7"])
    monkeypatch.setattr(UserSigner, "ask_one", lambda self: self._dummy_chat)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    config = signer.ask_for_config()

    assert config.random_seconds == 7


@pytest.mark.parametrize("raw", ["0", "", "12"])
def test_valid_random_seconds_accepted_first_time(monkeypatch, tmp_path, raw):
    signer = _make_signer_with_chat(tmp_path)
    inputs = iter(["n", "", raw])
    monkeypatch.setattr(UserSigner, "ask_one", lambda self: self._dummy_chat)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    config = signer.ask_for_config()

    assert config.random_seconds == int(float(raw or "0"))
