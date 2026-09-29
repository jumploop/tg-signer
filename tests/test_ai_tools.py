"""Tests for tg_signer.ai_tools.OpenAIConfigManager."""

import pytest

from tg_signer import ai_tools
from tg_signer.ai_tools import OpenAIConfigManager


def test_save_and_load_file_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    manager = OpenAIConfigManager(tmp_path)
    manager.save_config(
        "sk-test", base_url="https://example.com/v1", model="gpt-4o-mini"
    )
    assert (tmp_path / ".openai_config.json").is_file()
    assert manager.load_config() == {
        "api_key": "sk-test",
        "base_url": "https://example.com/v1",
        "model": "gpt-4o-mini",
    }


def test_load_config_prefers_env_vars(tmp_path, monkeypatch):
    manager = OpenAIConfigManager(tmp_path)
    manager.save_config("sk-file", model="file-model")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    cfg = manager.load_config()
    assert cfg["api_key"] == "sk-env"
    assert cfg["model"] == "env-model"


def test_has_config_env_only(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert OpenAIConfigManager(tmp_path).has_config()


def test_has_config_file_only(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    manager = OpenAIConfigManager(tmp_path)
    manager.save_config("sk-file")
    assert manager.has_config()


def test_has_config_false_when_no_source(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not OpenAIConfigManager(tmp_path).has_config()


def test_load_config_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert OpenAIConfigManager(tmp_path).load_config() is None


@pytest.mark.asyncio
async def test_test_openai_connection_calls_models_list(monkeypatch):
    class FakeModels:
        async def list(self):
            return []

    class FakeClient:
        models = FakeModels()
        closed = False

        async def close(self):
            self.closed = True

    client = FakeClient()
    monkeypatch.setattr(ai_tools, "get_openai_client", lambda **_kwargs: client)

    ok, message = await ai_tools.test_openai_connection(
        "sk-test", "https://example.com/v1", "gpt-test"
    )

    assert ok
    assert message == "连接成功，模型：gpt-test"
    assert client.closed


@pytest.mark.asyncio
async def test_calculate_problem_handles_none_content(monkeypatch):
    from tg_signer.ai_tools import AITools

    class FakeChoice:
        def __init__(self):
            self.message = type("M", (), {"content": None})()

    class FakeCompletion:
        choices = [FakeChoice()]

    class FakeCompletions:
        async def create(self, **kwargs):
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(ai_tools, "get_openai_client", lambda **_kwargs: FakeClient())
    tools = AITools({"api_key": "sk-test"})
    assert await tools.calculate_problem("1+1=?") == ""


class _FakeCompletions:
    """把 completions.create 固定返回指定 content 的替身。"""

    def __init__(self, content):
        self._content = content

    async def create(self, **_kwargs):
        message = type("Message", (), {"content": self._content})()
        choice = type("Choice", (), {"message": message})()
        return type("Completion", (), {"choices": [choice]})()


def _tools_with_content(monkeypatch, content):
    client = type(
        "Client",
        (),
        {"chat": type("Chat", (), {"completions": _FakeCompletions(content)})()},
    )()
    monkeypatch.setattr(ai_tools, "get_openai_client", lambda **_kwargs: client)
    return ai_tools.AITools({"api_key": "sk-test", "model": "fake-model"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        None,  # content 为空
        "",  # content 为空串
        "我看不清这张图",  # 非 JSON
        '{"reason": "随便选一个"}',  # 缺 option 字段
        '{"option": "第一个"}',  # option 不是整数
        "[1, 2, 3]",  # 顶层不是对象
    ],
)
async def test_choose_option_by_image_returns_minus_one_on_bad_output(
    monkeypatch, content
):
    """模型输出异常必须收敛成 -1,而不是把解析异常抛给签到主循环。"""
    tools = _tools_with_content(monkeypatch, content)
    result = await tools.choose_option_by_image(b"img", "q", [(0, "A"), (1, "B")])
    assert result == -1


@pytest.mark.asyncio
async def test_choose_option_by_image_parses_option_field(monkeypatch):
    tools = _tools_with_content(monkeypatch, '{"option": 1, "reason": "ok"}')
    result = await tools.choose_option_by_image(b"img", "q", [(0, "A"), (1, "B")])
    assert result == 1


@pytest.mark.asyncio
async def test_get_reply_returns_empty_string_when_content_missing(monkeypatch):
    """content 为 None 时返回空串,避免把 None 传给 send_message。"""
    tools = _tools_with_content(monkeypatch, None)
    assert await tools.get_reply("prompt", "query") == ""
