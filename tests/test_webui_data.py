"""Tests for tg_signer.webui.data module."""

import re

import pytest

from tg_signer.webui import data


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
    """批量生成时名称仍能保持互相不重复。"""
    workdir = tmp_path
    names = [
        data.generate_random_config_name("signer", {"title": "测试"}, workdir=workdir)
        for _ in range(100)
    ]
    assert len(set(names)) == len(names)  # 全部互不相同
    for name in names:
        assert re.fullmatch(r"sign_测试_[0-9a-f]{16}", name)


def test_list_task_names_ignores_dirs_without_config(tmp_path):
    workdir = tmp_path
    real_dir = workdir / "signs" / "real_task"
    real_dir.mkdir(parents=True)
    (real_dir / "config.json").write_text("{}", encoding="utf-8")
    # 删除配置后残留的目录(无 config.json)不应再出现在配置列表
    (workdir / "signs" / "ghost_task" / "legacy").mkdir(parents=True)
    assert data.list_task_names("signer", workdir) == ["real_task"]


def test_delete_config_removes_whole_dir_and_records(tmp_path):
    workdir = tmp_path
    task_dir = workdir / "signs" / "my_task"
    task_dir.mkdir(parents=True)
    (task_dir / "config.json").write_text("{}", encoding="utf-8")
    (task_dir / "1001" / "sign_record.json").mkdir(parents=True)
    (task_dir / "sign_record.json").write_text("[]", encoding="utf-8")
    deleted = data.delete_config("signer", "my_task", workdir=workdir)
    assert deleted == task_dir / "config.json"
    assert not task_dir.exists()
    assert data.list_task_names("signer", workdir) == []


# ---------------------------------------------------------------------------
# resolve_chat_id_for_selector (配置 ↔ 群组/频道 反向联动)
# ---------------------------------------------------------------------------


_CHATS_FIXTURE = {
    "123": {"id": 123, "username": "chan_a", "title": "频道A", "type": "channel"},
    "456": {"id": 456, "username": "grp_b", "title": "群B", "type": "group"},
}


@pytest.mark.parametrize(
    "requested,expected",
    [
        (123, "123"),  # int 值直接命中
        ("456", "456"),  # 字符串数字
        ("@chan_a", "123"),  # @username
        ("GRP_B", "456"),  # 裸 username,大小写不敏感
        ("@GRP_B", "456"),  # @ 前缀 + 大小写不敏感
    ],
)
def test_resolve_chat_id_for_selector_hits(requested, expected):
    assert data.resolve_chat_id_for_selector(requested, _CHATS_FIXTURE) == expected


@pytest.mark.parametrize(
    "requested",
    [None, True, 999, "999", "@nope", "", " ", "@", {}, 0],
)
def test_resolve_chat_id_for_selector_misses(requested):
    assert data.resolve_chat_id_for_selector(requested, _CHATS_FIXTURE) is None


def test_resolve_chat_id_for_selector_empty_dict():
    assert data.resolve_chat_id_for_selector(123, {}) is None
    assert data.resolve_chat_id_for_selector("@chan_a", {}) is None


def test_ui_state_has_selected_chat_id_default_none():
    state = data.UIState()
    assert state.selected_chat_id is None


def test_ui_state_selected_chat_id_roundtrip():
    state = data.UIState()
    state.selected_chat_id = 123
    assert state.selected_chat_id == 123
    state.selected_chat_id = "@chan_a"
    assert state.selected_chat_id == "@chan_a"
