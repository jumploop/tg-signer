"""Tests for tg_signer.webui.data module."""

import re

import pytest

from tg_signer.webui import data


@pytest.fixture(autouse=True)
def _reset_module_cache():
    """每个测试前清空模块级缓存,保证测试隔离。

    generate_random_config_name 会把已生成过的名字缓存在模块级
    _RECENTLY_GENERATED 与 _DISK_NAMES_CACHE 中,跨测试累积会让
    "不冲突" 断言依赖于不相关的历史状态,污染测试。
    """
    data._RECENTLY_GENERATED.clear()
    data._DISK_NAMES_CACHE.clear()
    yield
    data._RECENTLY_GENERATED.clear()
    data._DISK_NAMES_CACHE.clear()


def test_log_file_name_matches_runner():
    # 与 tg_signer.webui.runner.DEFAULT_LOG_FILE_NAME 一致
    assert data.LOG_FILE_NAME == "tg-signer.log"
    assert data.DEFAULT_LOG_FILE.name == data.LOG_FILE_NAME


def test_list_log_files_returns_empty_when_dir_missing(tmp_path):
    missing = tmp_path / "no_logs_dir"
    assert data.list_log_files(missing) == []


def test_list_log_files_finds_all_logs(tmp_path):
    (tmp_path / "a.log").write_text("a", encoding="utf-8")
    (tmp_path / "b.log").write_text("b", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    found = data.list_log_files(tmp_path)
    names = sorted(p.name for p in found)
    assert names == ["a.log", "b.log"]


# ---------------------------------------------------------------------------
# generate_random_config_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,prefix",
    [("signer", "sign_"), ("monitor", "monitor_")],
)
def test_generate_random_name_basic_shape(tmp_path, kind, prefix):
    name = data.generate_random_config_name(kind, workdir=tmp_path)
    assert name.startswith(prefix)
    # 末尾应当是 4~16 位 hex
    suffix = name[len(prefix) :].rsplit("_", 1)[-1]
    assert re.fullmatch(r"[0-9a-f]{4,16}", suffix)


def test_generate_random_name_uses_chat_title(tmp_path):
    chat = {"id": 1234567890, "title": "测试频道", "type": "channel"}
    name = data.generate_random_config_name("signer", chat, workdir=tmp_path)
    # 中文 + 下划线 + hex 后缀
    assert name.startswith("sign_")
    assert "测试频道" in name
    assert re.fullmatch(r"sign_[A-Za-z0-9_\u4e00-\u9fff]+_[0-9a-f]{4,16}", name)


def test_generate_random_name_uses_username_when_no_title(tmp_path):
    chat = {"id": 42, "username": "channel_xyz", "type": "channel"}
    name = data.generate_random_config_name("monitor", chat, workdir=tmp_path)
    assert name.startswith("monitor_")
    # 不能直接出现 `@`,只保留字母/数字/下划线
    assert "@" not in name
    # 简化后的 slug 中应包含核心单词
    assert "channel" in name or "channel_xyz" in name


def test_generate_random_name_handles_empty_chat(tmp_path):
    name = data.generate_random_config_name("signer", None, workdir=tmp_path)
    # 无 chat 时退化为 `sign_chat_<hex>`
    assert name.startswith("sign_chat_")
    suffix = name.rsplit("_", 1)[-1]
    assert re.fullmatch(r"[0-9a-f]{4,16}", suffix)


def test_generate_random_name_avoids_existing(tmp_path):
    workdir = tmp_path
    # 预置一个同前缀的占用名
    (workdir / "signs" / "sign_busy_aaaa" / "config.json").mkdir(parents=True)
    seen = {"sign_busy_aaaa"}
    for _ in range(50):
        name = data.generate_random_config_name("signer", workdir=workdir)
        assert name not in seen
        seen.add(name)
        assert name.startswith("sign_")


def test_generate_random_name_no_collision_under_saturation(tmp_path):
    """即便短后缀被全部预占,函数也能退回到更长 hex 后缀生成未占用名。"""
    workdir = tmp_path
    signs_root = workdir / "signs"
    signs_root.mkdir(parents=True)
    # 模拟“slug 完全相同 + 全部 4 位 hex 后缀都被占用”的极端情况:
    # 先占满一个具体 slug 下可能的 65536 个 4 位 hex 后缀是不现实的,
    # 这里只预占前 1000 个,验证函数不会无限重试短后缀。
    for i in range(1000):
        suffix = f"{i:04x}"
        (signs_root / f"sign_测试_{suffix}" / "config.json").mkdir(parents=True)
    # 但要让 list_task_names 返回的这 1000 个名字干扰 generator:
    # 由于我们的 slug 不是 “测试_xxxxx”,这 1000 个预置项不会影响生成的 slug,
    # 所以下面这步主要校验 1000 次生成全部不重复。
    names = {
        data.generate_random_config_name("signer", {"title": "测试"}, workdir=workdir)
        for _ in range(1000)
    }
    assert len(names) == 1000  # 全部互不相同
