"""Tests for tg_signer.ai_tools.OpenAIConfigManager."""

from pathlib import Path

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


def test_save_config_restricts_file_permissions(tmp_path, monkeypatch):
    """落盘后要把 .openai_config.json 收紧到仅属主可读写。

    文件里是明文 API Key,默认 umask 常见 0644,同机其他用户可直接读到。
    现在写入改为「同目录临时文件 + os.replace」原子写,所以临时文件也必须在
    改名**之前**就收紧权限 —— 否则在 umask 0644 下,Key 会有一瞬间对同机
    其他用户可读,只收紧最终文件挡不住这一点。
    """
    calls = []

    def _spy(path, mode=0o600):
        calls.append((Path(path), mode))
        return True

    monkeypatch.setattr(ai_tools, "restrict_file_permissions", _spy)

    final = tmp_path / ".openai_config.json"
    OpenAIConfigManager(tmp_path).save_config("sk-test", model="gpt-4o-mini")

    assert calls, "restrict_file_permissions 未被调用"
    assert calls[-1] == (final, 0o600), "最终配置文件权限未收紧"
    assert all(mode == 0o600 for _path, mode in calls), "存在未收紧的中间文件"
    assert all(path.parent == tmp_path for path, _mode in calls)
    # 不留临时文件
    assert list(tmp_path.glob("*.tmp")) == []


def test_save_config_is_atomic_and_keeps_old_key_on_failure(tmp_path, monkeypatch):
    """保存 API Key 必须原子：写失败时旧文件不能被截断。

    回归：原来直接 open(path, "w")，它会先截断再写。磁盘满 / 进程被杀 /
    被杀软打断时，用户已保存的 Key 就变成一个空文件或半截 JSON，没有备份。
    """
    import json as _json

    manager = OpenAIConfigManager(tmp_path)
    manager.save_config("sk-original", model="gpt-4o-mini")
    before = _json.loads((tmp_path / ".openai_config.json").read_text(encoding="utf-8"))
    assert before["api_key"] == "sk-original"

    def _boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(ai_tools.os, "replace", _boom)

    with pytest.raises(OSError):
        manager.save_config("sk-new", model="gpt-4o-mini")

    after = _json.loads((tmp_path / ".openai_config.json").read_text(encoding="utf-8"))
    assert after["api_key"] == "sk-original", "写失败把已有 Key 弄丢了"
    assert list(tmp_path.glob("*.tmp")) == [], "失败后残留临时文件"


def test_save_config_creates_missing_workdir(tmp_path):
    """workdir 不存在时必须先建目录。

    回归：save_config 直接往 <workdir>/.openai_config.json 写，默认 workdir
    `.signer` 在新克隆的仓库里本来就不存在 —— `tg-signer llm-config` 会在用户
    输完 Key 之后才抛 FileNotFoundError，刚敲进去的 Key 全丢。
    """
    workdir = tmp_path / "fresh" / "nested" / ".signer"
    assert not workdir.exists()

    OpenAIConfigManager(workdir).save_config("sk-test", model="gpt-4o-mini")

    assert (workdir / ".openai_config.json").is_file()
