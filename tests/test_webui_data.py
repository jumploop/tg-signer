"""Tests for tg_signer.webui.data module."""

import json
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


def test_generate_random_name_basic_shape(tmp_path):
    prefix = "sign_"
    name = data.generate_random_config_name("signer", workdir=tmp_path)
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
    name = data.generate_random_config_name("signer", chat, workdir=tmp_path)
    assert name.startswith("sign_")
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


def test_generate_random_name_supports_automation(tmp_path):
    workdir = tmp_path
    # automation 走 automations/ 目录,不能复用 list_task_names
    (workdir / "automations" / "auto_busy_aaaa").mkdir(parents=True)
    (workdir / "automations" / "auto_busy_aaaa" / "config.json").write_text(
        "{}", encoding="utf-8"
    )
    name = data.generate_random_config_name(
        "automation", {"title": "My Group"}, workdir=workdir
    )
    assert name.startswith("auto_My_Group_")
    assert name != "auto_busy_aaaa"
    assert re.fullmatch(r"auto_My_Group_[0-9a-f]{4,16}", name)


def test_list_task_names_ignores_dirs_without_config(tmp_path):
    workdir = tmp_path
    real_dir = workdir / "signs" / "real_task"
    real_dir.mkdir(parents=True)
    (real_dir / "config.json").write_text("{}", encoding="utf-8")
    # 删除配置后残留的目录(无 config.json)不应再出现在配置列表
    (workdir / "signs" / "ghost_task" / "legacy").mkdir(parents=True)
    assert data.list_task_names("signer", workdir) == ["real_task"]


def _write_user_cache(workdir, user_id, chats):
    user_dir = workdir / "users" / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "me.json").write_text(
        json.dumps({"id": user_id, "first_name": "Tester"}), encoding="utf-8"
    )
    (user_dir / "latest_chats.json").write_text(json.dumps(chats), encoding="utf-8")


def test_load_group_chats_accepts_enum_style_types(tmp_path):
    """CLI 登录经 Object.default 序列化的 'ChatType.BOT' 等类型也应被识别。"""
    _write_user_cache(
        tmp_path,
        1,
        [
            {"id": 10, "title": "群", "type": "ChatType.GROUP", "username": None},
            {"id": 11, "title": "机器人", "type": "ChatType.BOT", "username": "bot"},
            {"id": 12, "title": "私人", "type": "ChatType.PRIVATE", "username": None},
        ],
    )
    chats = data.load_group_chats(tmp_path)
    ids = {c["id"] for c in chats}
    assert ids == {10, 11}
    # 输出中的 type 归一化为小写名称
    assert {c["id"]: c["type"] for c in chats} == {10: "group", 11: "bot"}


def test_load_group_chats_accepts_plain_types(tmp_path):
    """WebUI 登录写入的 'bot' 等小写类型同样被识别。"""
    _write_user_cache(
        tmp_path,
        1,
        [
            {"id": 20, "title": "频道", "type": "channel", "username": "ch"},
            {"id": 21, "title": "群", "type": "supergroup", "username": None},
        ],
    )
    chats = data.load_group_chats(tmp_path)
    assert {c["id"] for c in chats} == {20, 21}


def test_list_automation_names(tmp_path):
    workdir = tmp_path
    (workdir / "automations" / "a_json").mkdir(parents=True)
    (workdir / "automations" / "a_json" / "config.json").write_text(
        "{}", encoding="utf-8"
    )
    (workdir / "automations" / "b_yaml").mkdir(parents=True)
    (workdir / "automations" / "b_yaml" / "config.yaml").write_text(
        "rules: []", encoding="utf-8"
    )
    (workdir / "automations" / "c_yml").mkdir(parents=True)
    (workdir / "automations" / "c_yml" / "config.yml").write_text(
        "rules: []", encoding="utf-8"
    )
    # 残留空目录不应出现在配置列表
    (workdir / "automations" / "ghost").mkdir(parents=True)
    assert data.list_automation_names(workdir) == ["a_json", "b_yaml", "c_yml"]


def test_list_automation_names_missing_dir(tmp_path):
    assert data.list_automation_names(tmp_path) == []


def test_automation_config_json_roundtrip(tmp_path):
    workdir = tmp_path
    payload = {
        "rules": [
            {
                "id": "rule_1",
                "triggers": [{"type": "message", "params": {"chat_id": "@chan"}}],
                "handlers": [{"handler": "send_text", "params": {"text": "ok"}}],
            }
        ]
    }
    saved = data.save_automation_config("auto_json", payload, workdir)
    assert saved.name == "config.json"
    assert (workdir / "automations" / "auto_json" / "config.json").is_file()

    entry = data.load_automation_config("auto_json", workdir)
    assert entry.payload["rules"][0]["id"] == "rule_1"
    assert entry.payload["rules"][0]["triggers"][0]["type"] == "message"


def test_automation_config_yaml_read(tmp_path):
    pytest.importorskip("yaml")
    workdir = tmp_path
    auto_dir = workdir / "automations" / "auto_yaml"
    auto_dir.mkdir(parents=True)
    (auto_dir / "config.yaml").write_text(
        "rules:\n"
        "  - id: rule_1\n"
        "    triggers:\n"
        "      - type: message\n"
        "        params:\n"
        "          chat_id: '@chan'\n"
        "    handlers:\n"
        "      - handler: send_text\n"
        "        params:\n"
        "          text: ok\n",
        encoding="utf-8",
    )
    entry = data.load_automation_config("auto_yaml", workdir)
    assert entry.path.name == "config.yaml"
    assert entry.payload["rules"][0]["id"] == "rule_1"

    # 保存后写回标准 JSON（CLI 解析 JSON 优先）
    data.save_automation_config("auto_yaml", entry.payload, workdir)
    assert (auto_dir / "config.json").is_file()


def test_automation_config_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        data.load_automation_config("ghost", tmp_path)


def test_automation_config_save_rejects_invalid(tmp_path):
    with pytest.raises(ValueError):
        data.save_automation_config("bad", {"rules": [{"id": "x"}]}, workdir=tmp_path)


def test_automation_config_delete_removes_dir(tmp_path):
    task_dir = tmp_path / "automations" / "gone"
    task_dir.mkdir(parents=True)
    (task_dir / "config.json").write_text("{}", encoding="utf-8")
    deleted = data.delete_automation_config("gone", tmp_path)
    assert deleted == task_dir / "config.json"
    assert not task_dir.exists()
    assert data.list_automation_names(tmp_path) == []


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


# ---------------------------------------------------------------------------
# save_config / save_automation_config 的校验错误明细
# ---------------------------------------------------------------------------


def test_save_config_rejects_invalid_cron(tmp_path):
    payload = {
        "chats": [{"chat_id": 1, "actions": []}],
        "sign_at": "不是 cron",
    }
    with pytest.raises(ValueError, match="sign_at"):
        data.save_config("signer", "bad", payload, workdir=tmp_path)
    assert not (tmp_path / "signs" / "bad").exists()


def test_save_config_error_lists_field_path(tmp_path):
    payload = {
        "chats": [{"chat_id": 1, "actions": "not-a-list"}],
        "sign_at": "0 6 * * *",
    }
    with pytest.raises(ValueError, match=r"chats\.0\.actions"):
        data.save_config("signer", "bad", payload, workdir=tmp_path)


def test_save_automation_config_error_lists_field_path(tmp_path):
    payload = {
        "rules": [
            {
                "id": "r1",
                "enabled": True,
                "triggers": [{"type": "message", "params": {"chat_id": 123}}],
                "handlers": [{"handler": "send_text", "params": {"text": "hi"}}],
            }
        ]
    }
    payload["rules"][0]["triggers"][0]["params"]["nope"] = 1
    with pytest.raises(ValueError, match=r"triggers\.0\..*params\.nope"):
        data.save_automation_config("bad", payload, workdir=tmp_path)


def test_load_config_migrates_legacy_v1_file(tmp_path):
    """V1 老配置放在磁盘上也必须能加载并升级。"""
    task_dir = tmp_path / "signs" / "legacy"
    task_dir.mkdir(parents=True)
    (task_dir / "config.json").write_text(
        json.dumps(
            {
                "chat_id": 123,
                "sign_text": "老配置",
                "sign_at": "06:00:00",
                "random_seconds": 0,
            }
        ),
        encoding="utf-8",
    )
    entry = data.load_config("signer", "legacy", tmp_path)
    assert entry.updated_from_old is True
    assert entry.payload["chats"][0]["chat_id"] == 123
