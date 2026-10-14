import asyncio

import pytest
from click.testing import CliRunner

import tg_signer.cli.signer as signer_cli


class DummySigner:
    def __init__(self):
        self.calls = []

    def app_run(self, coroutine=None):
        if coroutine is not None:
            asyncio.run(coroutine)

    async def send_text(
        self, chat_id, text, delete_after=None, message_thread_id=None, **kwargs
    ):
        self.calls.append(
            {
                "method": "send_text",
                "chat_id": chat_id,
                "text": text,
                "delete_after": delete_after,
                "message_thread_id": message_thread_id,
                "kwargs": kwargs,
            }
        )

    async def send_dice_cli(
        self, chat_id, emoji, delete_after=None, message_thread_id=None, **kwargs
    ):
        self.calls.append(
            {
                "method": "send_dice_cli",
                "chat_id": chat_id,
                "emoji": emoji,
                "delete_after": delete_after,
                "message_thread_id": message_thread_id,
                "kwargs": kwargs,
            }
        )

    async def schedule_messages(
        self,
        chat_id,
        text,
        crontab,
        next_times,
        random_seconds,
        message_thread_id=None,
    ):
        self.calls.append(
            {
                "method": "schedule_messages",
                "chat_id": chat_id,
                "text": text,
                "crontab": crontab,
                "next_times": next_times,
                "random_seconds": random_seconds,
                "message_thread_id": message_thread_id,
            }
        )

    async def get_schedule_messages(self, chat_id):
        self.calls.append(
            {
                "method": "get_schedule_messages",
                "chat_id": chat_id,
            }
        )

    async def list_topics(self, chat_id, limit=20):
        self.calls.append(
            {
                "method": "list_topics",
                "chat_id": chat_id,
                "limit": limit,
            }
        )

    async def run_once(self, num_of_dialogs, folder=None):
        self.calls.append(
            {
                "method": "run_once",
                "num_of_dialogs": num_of_dialogs,
                "folder": folder,
            }
        )


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def dummy_signer(monkeypatch):
    dummy = DummySigner()
    monkeypatch.setattr(signer_cli, "get_signer", lambda *_args, **_kwargs: dummy)
    return dummy


@pytest.mark.parametrize(
    ("args", "method", "field", "expected"),
    [
        (
            ["send-text", "--message-thread-id", "1", "123456", "checkin"],
            "send_text",
            "message_thread_id",
            1,
        ),
        (["send-text", "@neo", "checkin"], "send_text", "chat_id", "@neo"),
        (
            ["send-dice", "--message-thread-id", "1", "123456", "🎲"],
            "send_dice_cli",
            "message_thread_id",
            1,
        ),
        (["send-dice", "@neo", "🎲"], "send_dice_cli", "chat_id", "@neo"),
        (
            [
                "schedule-messages",
                "--crontab",
                "0 6 * * *",
                "--message-thread-id",
                "1",
                "123456",
                "checkin",
            ],
            "schedule_messages",
            "message_thread_id",
            1,
        ),
        (
            ["schedule-messages", "--crontab", "0 6 * * *", "@neo", "checkin"],
            "schedule_messages",
            "chat_id",
            "@neo",
        ),
        (
            ["list-schedule-messages", "@neo"],
            "get_schedule_messages",
            "chat_id",
            "@neo",
        ),
        (
            ["list-topics", "--chat_id", "-1003763902761", "--limit", "50"],
            "list_topics",
            "chat_id",
            -1003763902761,
        ),
        (
            ["list-topics", "--chat_id", "@neo", "--limit", "50"],
            "list_topics",
            "chat_id",
            "@neo",
        ),
    ],
)
def test_message_thread_id_and_username_chat_ids(
    dummy_signer, runner, args, method, field, expected
):
    result = runner.invoke(signer_cli.tg_signer, args)

    assert result.exit_code == 0
    assert dummy_signer.calls[0]["method"] == method
    assert dummy_signer.calls[0][field] == expected


def test_bare_at_chat_id_reports_usage_error_not_traceback(dummy_signer, runner):
    """``send-text @ hello`` 必须给出用法错误，而不是裸 ValueError traceback。

    回归：``parse_chat_id`` 里 "@" 分支在 try 之外，
    ``parse_chat_id_or_username("@")`` 抛的 ValueError 会一路冒到终端。
    """
    result = runner.invoke(signer_cli.tg_signer, ["send-text", "@", "hello"])

    assert result.exit_code != 0
    assert "Traceback" not in (result.output + str(result.exception or ""))
    assert isinstance(result.exception, SystemExit)
