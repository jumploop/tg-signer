"""Tests for tg_signer.ai_tools.OpenAIConfigManager."""

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


def test_load_config_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert OpenAIConfigManager(tmp_path).load_config() is None
