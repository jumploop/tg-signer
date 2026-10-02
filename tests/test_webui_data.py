"""Tests for tg_signer.webui.data module."""

import json
import os
import re
import threading
import time

import pytest

from tg_signer.config import AutomationConfig, SignConfigV3
from tg_signer.webui import data


def test_log_file_name_matches_runner():
    # 与 tg_signer.webui.runner.DEFAULT_LOG_FILE_NAME 一致
    assert data.LOG_FILE_NAME == "tg-signer.log"
    assert data.DEFAULT_LOG_FILE.name == data.LOG_FILE_NAME


# ---------------------------------------------------------------------------
# 配置类型元数据：一张表管全部
# ---------------------------------------------------------------------------


def test_config_kinds_covers_every_kind_name_can_generate():
    """凡是能自动命名的 kind 都必须在表里有条目。

    判别性：以前目录名/配置类在 `CONFIG_META`、随机名前缀在 `NAME_PREFIXES`，
    `automation` 只存在于后者；两张表漏一张就是运行期 KeyError。
    """
    from typing import get_args

    for kind in get_args(data.NameGenKind):
        assert kind in data.CONFIG_KINDS, f"{kind} 缺少元数据条目"
        assert data.CONFIG_KINDS[kind].name_prefix


def test_only_signer_kind_has_a_signs_directory(tmp_path):
    assert data.CONFIG_KINDS["signer"].dir_name == "signs"
    assert data.CONFIG_KINDS["signer"].cfg_cls is SignConfigV3
    assert data.CONFIG_KINDS["automation"].dir_name is None
    assert data.CONFIG_KINDS["automation"].cfg_cls is AutomationConfig


def test_config_root_rejects_kinds_without_a_directory(tmp_path):
    """没有目录布局的 kind 走 `_config_root` 必须显式报错，不能静默拼出错误路径。"""
    assert data._config_root("signer", tmp_path) == tmp_path / "signs"
    with pytest.raises(ValueError, match="automation"):
        data._config_root("automation", tmp_path)


def test_uses_dir_layout_excludes_automation():
    """目录守卫不能退化成成员判断。

    这是合并两张表时最容易踩的坑：`automation` 现在也在 `CONFIG_KINDS` 里，
    若守卫写成成员判断，就会把它放行到一个并不存在的 `signs/` 目录上
    （`server.py` 的 4 处「不支持的配置类型」守卫依赖这个区分）。
    """
    assert data.uses_dir_layout("signer") is True
    assert data.uses_dir_layout("automation") is False
    assert data.uses_dir_layout("unknown") is False


def test_generated_name_prefix_comes_from_the_shared_table(tmp_path):
    assert data.generate_random_config_name("signer", workdir=tmp_path).startswith(
        data.CONFIG_KINDS["signer"].name_prefix + "_"
    )
    assert data.generate_random_config_name("automation", workdir=tmp_path).startswith(
        data.CONFIG_KINDS["automation"].name_prefix + "_"
    )


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


def test_list_log_files_includes_task_subdirectories(tmp_path):
    """runner.py 把任务日志写到 logs/<kind>-<account>/ 下，非递归就全列不出来。"""
    (tmp_path / "tg-signer.log").write_text("", encoding="utf-8")
    sub = tmp_path / "signer-demo"
    sub.mkdir()
    (sub / "tg-signer.log").write_text("task output\n", encoding="utf-8")

    found = data.list_log_files(tmp_path)
    assert (sub / "tg-signer.log").resolve() in [p.resolve() for p in found]


def test_list_log_files_puts_non_empty_and_recent_first(tmp_path):
    """排序即默认选中项：空文件必须排在有内容的文件之后。"""
    empty = tmp_path / "tg-signer.log"
    empty.write_text("", encoding="utf-8")
    older = tmp_path / "older.log"
    older.write_text("old\n", encoding="utf-8")
    newer = tmp_path / "newer.log"
    newer.write_text("new\n", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    found = data.list_log_files(tmp_path)
    assert [p.name for p in found] == ["newer.log", "older.log", "tg-signer.log"]


# ---------------------------------------------------------------------------
# load_logs / _resolve_log_path：只能读 log_dir 下的文件
# ---------------------------------------------------------------------------


def test_load_logs_reads_name_and_absolute_path_under_log_dir(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    main_log = log_dir / "tg-signer.log"
    main_log.write_text("a\nb\n", encoding="utf-8")

    for value in (None, "tg-signer.log", str(main_log)):
        resolved, lines = data.load_logs(limit=10, log_path=value, log_dir=log_dir)
        assert resolved == main_log.resolve()
        assert lines[:2] == ["a", "b"]


def test_load_logs_defaults_to_main_log_file(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "tg-signer.log").write_text("x\n", encoding="utf-8")

    resolved, lines = data.load_logs(log_dir=log_dir)
    assert resolved.name == data.LOG_FILE_NAME
    assert lines[0] == "x"


def test_load_logs_without_path_falls_back_to_non_empty_log(tmp_path):
    """0 字节的主日志不该再是默认落点，否则日志页一进来就是「暂无日志内容」。"""
    log_dir = tmp_path / "logs"
    (log_dir / "signer-demo").mkdir(parents=True)
    (log_dir / "tg-signer.log").write_text("", encoding="utf-8")
    task_log = log_dir / "signer-demo" / "tg-signer.log"
    task_log.write_text("task line\n", encoding="utf-8")

    resolved, lines = data.load_logs(log_dir=log_dir)
    assert resolved == task_log.resolve()
    assert lines[0] == "task line"


@pytest.mark.parametrize(
    "make_target",
    [
        lambda tmp_path: tmp_path / "acc.session_string",  # workdir 根下的敏感文件
        lambda tmp_path: tmp_path / ".." / "outside.log",  # 上级目录
    ],
    ids=["sensitive-file", "parent-dir"],
)
def test_load_logs_rejects_path_outside_log_dir(tmp_path, make_target):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    target = make_target(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("SECRET\n", encoding="utf-8")

    with pytest.raises(ValueError, match="路径越界"):
        data.load_logs(log_path=target, log_dir=log_dir)


def test_load_logs_reads_task_log_in_one_level_subdirectory(tmp_path):
    log_dir = tmp_path / "logs"
    (log_dir / "signer-demo").mkdir(parents=True)
    task_log = log_dir / "signer-demo" / "tg-signer.log"
    task_log.write_text("task line\n", encoding="utf-8")

    for value in ("signer-demo/tg-signer.log", str(task_log)):
        resolved, lines = data.load_logs(limit=10, log_path=value, log_dir=log_dir)
        assert resolved == task_log.resolve()
        assert lines[0] == "task line"


@pytest.mark.parametrize(
    "relative",
    ["signer-demo/nested/tg-signer.log", "../outside.log", "tg-signer.session_string"],
    ids=["too-deep", "outside", "non-log-suffix"],
)
def test_load_logs_rejects_paths_outside_allowed_log_shape(tmp_path, relative):
    """放宽到一层子目录后，越界/敏感文件/非 .log 仍必须被拒。"""
    log_dir = tmp_path / "logs"
    nested = log_dir / "signer-demo" / "nested"
    nested.mkdir(parents=True)
    (nested / "tg-signer.log").write_text("SECRET\n", encoding="utf-8")
    (log_dir / "acc.session_string").write_text("SECRET\n", encoding="utf-8")
    (tmp_path / "outside.log").write_text("SECRET\n", encoding="utf-8")

    with pytest.raises(ValueError):
        data.load_logs(log_path=log_dir / relative, log_dir=log_dir)


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


def test_delete_config_raises_when_the_directory_cannot_be_removed(
    tmp_path, monkeypatch
):
    """删不掉时必须抛 ``OSError``，不能静默吞掉后照报成功。

    回归：删除走的是 ``shutil.rmtree(..., ignore_errors=True)``。Windows 上只要
    目录里有文件被别的句柄占着（另一个请求正开着它、编辑器、tail、杀软……），
    ``rmtree`` 就失败，而这个失败被 ignore_errors 吃掉 —— 调用方
    ``DELETE /api/configs/...`` 仍然返回 ``{"ok": true}``：前端弹「已删除」，
    列表一刷新配置又出现了，用户被告知配置已被销毁、实际一点没动。
    """

    def _busy(directory, *args, **kwargs):
        raise PermissionError(32, "另一个进程正在使用此文件")

    monkeypatch.setattr(data.shutil, "rmtree", _busy)

    task_dir = tmp_path / "signs" / "my_task"
    task_dir.mkdir(parents=True)
    (task_dir / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(OSError):
        data.delete_config("signer", "my_task", workdir=tmp_path)
    assert task_dir.is_dir(), "删除失败却把配置目录弄丢了"

    # 自动化的删除走同一个 helper，语义必须一致。
    auto_dir = tmp_path / "automations" / "auto_task"
    auto_dir.mkdir(parents=True)
    (auto_dir / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(OSError):
        data.delete_automation_config("auto_task", tmp_path)
    assert auto_dir.is_dir()


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


# 名称必须是单一路径分量:否则删除会落到配置根目录之外
# (甚至整个 workdir)。
_TRAVERSAL_NAMES = ["..", ".", "", "a/b", "a\\b", "sub\\..\\.."]


@pytest.mark.parametrize("name", _TRAVERSAL_NAMES)
def test_delete_config_rejects_non_component_name(tmp_path, name):
    workdir = tmp_path
    task_dir = workdir / "signs" / "my_task"
    task_dir.mkdir(parents=True)
    (task_dir / "config.json").write_text("{}", encoding="utf-8")
    (workdir / "config.json").write_text("{}", encoding="utf-8")
    (workdir / "data.sqlite3").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError):
        data.delete_config("signer", name, workdir=workdir)

    # workdir 与其中的配置必须原样保留
    assert task_dir.exists()
    assert (workdir / "signs").exists()
    assert (workdir / "data.sqlite3").exists()


@pytest.mark.parametrize("name", _TRAVERSAL_NAMES)
def test_delete_automation_config_rejects_non_component_name(tmp_path, name):
    workdir = tmp_path
    task_dir = workdir / "automations" / "gone"
    task_dir.mkdir(parents=True)
    (task_dir / "config.json").write_text("{}", encoding="utf-8")
    (workdir / "automations" / "config.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        data.delete_automation_config(name, workdir)

    assert task_dir.exists()
    assert (workdir / "automations").exists()


def test_delete_config_rejects_absolute_path(tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "config.json").write_text("{}", encoding="utf-8")

    workdir = tmp_path / "wd"
    (workdir / "signs").mkdir(parents=True)

    with pytest.raises(ValueError):
        data.delete_config("signer", str(victim), workdir=workdir)

    assert victim.exists()


@pytest.mark.parametrize("name", ["my_task", "签到任务", "task with space", "a.b-c_d"])
def test_delete_config_accepts_ordinary_names(tmp_path, name):
    # 合法名称(中文/空格/点横线下划线)必须仍然可以删除
    task_dir = tmp_path / "signs" / name
    task_dir.mkdir(parents=True)
    (task_dir / "config.json").write_text("{}", encoding="utf-8")

    deleted = data.delete_config("signer", name, workdir=tmp_path)

    assert deleted == task_dir / "config.json"
    assert not task_dir.exists()


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


# ---------------------------------------------------------------------------
# 配置读写的副作用与原子性
# ---------------------------------------------------------------------------


def _v1_payload():
    """一个会被自动迁移的 V1 配置。"""
    return {
        "chat_id": 123,
        "sign_text": "老配置",
        "sign_at": "06:00:00",
        "random_seconds": 0,
    }


def test_load_config_does_not_write_to_disk(tmp_path):
    """读配置不得产生写副作用。

    回归：``from_old`` 分支原本会 ``save_config(...)`` 回写，于是
    「打开配置」「列表页」这类纯读操作会改磁盘 —— 只读挂载或无写权限时，
    明明已经读成功却抛 OSError，整个页面 500；而且每次读都把配置截断重写一次。
    """
    cfg_file = tmp_path / "signs" / "old" / "config.json"
    cfg_file.parent.mkdir(parents=True)
    raw = json.dumps(_v1_payload(), ensure_ascii=False)
    cfg_file.write_text(raw, encoding="utf-8")

    entry = data.load_config("signer", "old", workdir=tmp_path)

    assert entry.updated_from_old is True, "仍应标记为「已从旧结构迁移」"
    assert cfg_file.read_text(encoding="utf-8") == raw, "读操作改写了磁盘"


def test_load_config_succeeds_on_read_only_workdir(tmp_path, monkeypatch):
    """配置目录不可写时，读取必须成功而不是抛 OSError。"""
    cfg_file = tmp_path / "signs" / "old" / "config.json"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(json.dumps(_v1_payload()), encoding="utf-8")

    real_open = open

    def _read_only_open(path, mode="r", *args, **kwargs):
        if "w" in mode and "signs" in str(path):
            raise PermissionError(f"拒绝写入: {path}")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", _read_only_open)

    entry = data.load_config("signer", "old", workdir=tmp_path)
    assert entry.name == "old"


def _v3_payload(chat_id=1, width=1):
    return {
        "sign_at": "0 6 * * *",
        "chats": [{"chat_id": chat_id, "actions": []}] * width,
    }


def test_save_config_never_leaves_a_partial_file(tmp_path, monkeypatch):
    """写到一半失败时不得留下残缺的 config.json。

    回归：直接 ``open(path, "w")`` 会先截断，``json.dump`` 途中抛异常就会把用户
    唯一的配置留在半个 JSON 的状态（且此后每次读都报「配置损坏」）。
    """
    data.save_config("signer", "ok", _v3_payload(), workdir=tmp_path)
    cfg_file = tmp_path / "signs" / "ok" / "config.json"
    before = cfg_file.read_text(encoding="utf-8")

    def _boom(*args, **kwargs):
        raise RuntimeError("磁盘满了")

    monkeypatch.setattr(data.json, "dump", _boom)
    with pytest.raises(RuntimeError):
        data.save_config("signer", "ok", _v3_payload(), workdir=tmp_path)

    assert cfg_file.read_text(encoding="utf-8") == before, "配置文件被写坏了"
    leftovers = [p.name for p in cfg_file.parent.iterdir() if ".tmp-" in p.name]
    assert leftovers == [], f"残留临时文件: {leftovers}"


def test_concurrent_save_and_load_never_break_each_other(tmp_path):
    """并发保存与读取配置时，两者都必须稳定成功。

    WebUI 是 FastAPI 线程池并发处理请求的，保存与打开配置会真实地同时发生。
    两个失败模式都要挡住：
    1. 非原子写 → 读者读到半个 JSON，报「配置损坏」；
    2. Windows 上 ``os.replace`` 要求目标无未共享删除的打开句柄，
       而 ``open(path, "r")`` 不共享删除 → 并发读直接把保存打成 WinError 5。
    """
    data.save_config("signer", "big", _v3_payload(0, width=400), workdir=tmp_path)

    stop = threading.Event()
    errors: list[str] = []

    def _reader():
        while not stop.is_set():
            try:
                data.load_config("signer", "big", workdir=tmp_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"reader: {exc!r}")

    def _writer():
        i = 0
        while not stop.is_set():
            i += 1
            try:
                data.save_config(
                    "signer", "big", _v3_payload(i, width=400), workdir=tmp_path
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"writer: {exc!r}")

    threads = [threading.Thread(target=_reader) for _ in range(3)]
    threads.append(threading.Thread(target=_writer))
    for t in threads:
        t.start()
    time.sleep(1.0)
    stop.set()
    for t in threads:
        t.join()

    assert errors == [], f"并发读写出现失败: {errors[:3]}"
    # 收尾：读到的最终内容必须是完整且合法的 JSON
    final = data.load_config("signer", "big", workdir=tmp_path)
    assert len(final.payload["chats"]) == 400


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


# ---------------------------------------------------------------------------
# 回归：import 副作用 / 脏 latest_chats.json
# ---------------------------------------------------------------------------


def test_get_workdir_can_resolve_without_creating(tmp_path):
    """create=False 时只解析路径，不落盘。

    模块级 ``state`` 过去在 import 阶段就 mkdir，于是「仅仅 import 一下」会在
    进程 CWD 下凭空建出 ``.signer`` —— 传了 --workdir 也照样建。
    """
    target = tmp_path / "never-created"
    resolved = data.get_workdir(target, create=False)
    assert resolved == target.resolve()
    assert not target.exists(), "create=False 仍然创建了目录"


def test_ui_state_create_false_does_not_touch_disk(tmp_path, monkeypatch):
    monkeypatch.delenv("TG_SIGNER_WORKDIR", raising=False)
    monkeypatch.setattr(data, "DEFAULT_WORKDIR", tmp_path / "import_side_effect")
    state = data.UIState(create=False)
    assert state.workdir == (tmp_path / "import_side_effect").resolve()
    assert not (tmp_path / "import_side_effect").exists()


@pytest.mark.parametrize("payload", [{}, None, "not-a-list"])
def test_load_group_chats_tolerates_malformed_latest_chats(tmp_path, payload):
    """latest_chats.json 内容不是数组时，不能把 /api/chats 打成 500。"""
    user_dir = tmp_path / "users" / "u1"
    user_dir.mkdir(parents=True)
    (user_dir / "me.json").write_text(json.dumps({"id": 1}), encoding="utf-8")
    (user_dir / "latest_chats.json").write_text(json.dumps(payload), encoding="utf-8")
    assert data.load_group_chats(tmp_path) == []


@pytest.mark.parametrize("payload", [None, [], "text", 3], ids=lambda p: repr(p))
def test_load_user_infos_skips_non_object_me_json(tmp_path, payload):
    """me.json 是合法 JSON 但不是对象时跳过该条目，不能把 /api/chats 打成 500。

    与 ``latest_chats.json`` 的非数组守卫同源：``null`` 会让下游
    ``info.data.get(...)`` 抛 AttributeError，``[]`` 抛 TypeError。
    """
    user_dir = tmp_path / "users" / "u1"
    user_dir.mkdir(parents=True)
    (user_dir / "me.json").write_text(json.dumps(payload), encoding="utf-8")

    assert data.load_user_infos(tmp_path) == []
    assert data.load_group_chats(tmp_path) == []


# ---------------------------------------------------------------------------
# tail_file：只应丢掉「文件末尾换行」产生的空段
# ---------------------------------------------------------------------------


def _write_log(tmp_path, content: bytes):
    path = tmp_path / "app.log"
    path.write_bytes(content)
    return path


def test_tail_file_drops_trailing_newline_artifact(tmp_path):
    """'l1\\nl2\\nl3\\n' 是 3 行，不能回出 4 项（末尾伪空行）。"""
    path = _write_log(tmp_path, b"l1\nl2\nl3\n")
    assert data.tail_file(path, limit=200) == ["l1", "l2", "l3"]


def test_tail_file_returns_limit_real_lines(tmp_path):
    """伪空行不再白占 limit 名额：limit=3 必须回满 3 行。"""
    path = _write_log(tmp_path, b"l1\nl2\nl3\n")
    assert data.tail_file(path, limit=3) == ["l1", "l2", "l3"]
    assert data.tail_file(path, limit=2) == ["l2", "l3"]


def test_tail_file_keeps_real_blank_lines(tmp_path):
    """中间的空行是真实空行，只有文件末尾那一个空段该丢。"""
    path = _write_log(tmp_path, b"l1\n\nl3\n")
    assert data.tail_file(path, limit=200) == ["l1", "", "l3"]


def test_tail_file_without_trailing_newline(tmp_path):
    path = _write_log(tmp_path, b"l1\nl2\nl3")
    assert data.tail_file(path, limit=200) == ["l1", "l2", "l3"]


def test_tail_file_handles_empty_file_and_lone_newline(tmp_path):
    assert data.tail_file(_write_log(tmp_path, b""), limit=10) == []
    # 只含一个换行的文件就是「一行空行」：换行空段丢掉后，空行本身要留下。
    assert data.tail_file(_write_log(tmp_path, b"\n"), limit=10) == [""]
    assert data.tail_file(tmp_path / "missing.log", limit=10) == []


def test_tail_file_reassembles_long_line_spanning_chunks(tmp_path):
    """跨多个 8KiB 块的长行必须原样拼回，不能被截断。"""
    long_line = "x" * 20000
    path = _write_log(tmp_path, f"{long_line}\nend\n".encode())
    assert data.tail_file(path, limit=200) == [long_line, "end"]


def test_tail_file_keeps_order_across_many_chunks(tmp_path):
    lines = [f"line{i:05d}" for i in range(3000)]
    path = _write_log(tmp_path, ("\n".join(lines) + "\n").encode())
    assert data.tail_file(path, limit=200) == lines[-200:]


def test_tail_file_preserves_utf8_split_across_chunks(tmp_path):
    """块边界劈开的多字节字符必须完好：拼行是按字节做的跨块重组。"""
    first = "中" * 8000
    content = (first + "\nend\n").encode("utf-8")
    path = _write_log(tmp_path, content)
    assert len(content) > 8192 * 2, "需要跨多个块才能覆盖边界劈裂"
    assert data.tail_file(path, limit=200) == [first, "end"]


# ---------------------------------------------------------------------------
# 签到记录：SQLite / 遗留 JSON 去重，以及损坏的 SQLite
# ---------------------------------------------------------------------------


def test_load_sign_records_dedups_two_part_legacy_json_against_sqlite(tmp_path):
    """同一个 2 段遗留文件在迁移到 SQLite 后只能出现一次。

    ``_record_target`` 对 ``signs/<task>/sign_record.json`` 给 user_id=None，
    而 ``SignRecordStore.resolve_record_target`` 会把它推断成当时唯一的 user_id
    ——两边键不一致，去重永远命中不了，「优先用已迁移的 SQLite 行」形同虚设。
    """
    from tg_signer.sign_record_store import SignRecordStore

    store = SignRecordStore(tmp_path)
    store.upsert_record("daily", "1001", "2024-01-01", "2024-01-01 06:00:00")

    # 只有一个 users/<id>，store 才能把 2 段布局推断到这个 user_id 上。
    user_dir = tmp_path / "users" / "1001"
    user_dir.mkdir(parents=True)
    (user_dir / "me.json").write_text("{}", encoding="utf-8")

    task_dir = tmp_path / "signs" / "daily"
    task_dir.mkdir(parents=True)
    (task_dir / "sign_record.json").write_text(
        json.dumps({"2024-01-01": "2024-01-01 06:00:00"}), encoding="utf-8"
    )

    records = data.load_sign_records(tmp_path)
    assert [(r.task, r.user_id) for r in records] == [("daily", "1001")]


def test_load_sign_records_dedups_two_json_layouts_without_sqlite(tmp_path):
    """两种 legacy JSON 布局解析出同一个 key 时只能出现一行。

    回归：``existing_keys`` 原本只在遍历 SQLite 分组时被填充，JSON 分支
    只查不加，于是 ``signs/<task>/sign_record.json`` 与
    ``signs/<task>/<user_id>/sign_record.json`` 会同时出现在记录页，
    且各自只带着一半的历史。
    """
    user_dir = tmp_path / "users" / "1001"
    user_dir.mkdir(parents=True)
    (user_dir / "me.json").write_text("{}", encoding="utf-8")

    three_part = tmp_path / "signs" / "daily" / "1001"
    three_part.mkdir(parents=True)
    (three_part / "sign_record.json").write_text(
        json.dumps({"2024-01-02": "2024-01-02 06:00:00"}), encoding="utf-8"
    )

    two_part = tmp_path / "signs" / "daily"
    two_part.mkdir(parents=True, exist_ok=True)
    (two_part / "sign_record.json").write_text(
        json.dumps({"2024-01-01": "2024-01-01 06:00:00"}), encoding="utf-8"
    )

    records = data.load_sign_records(tmp_path)
    assert [(r.task, r.user_id) for r in records] == [("daily", "1001")]


def test_load_sign_records_keeps_distinct_user_rows(tmp_path):
    """去重不能过度：不同 user_id 的记录仍要分别出现。"""
    from tg_signer.sign_record_store import SignRecordStore

    store = SignRecordStore(tmp_path)
    store.upsert_record("daily", "1001", "2024-01-01", "2024-01-01 06:00:00")

    record_file = tmp_path / "signs" / "daily" / "2002" / "sign_record.json"
    record_file.parent.mkdir(parents=True)
    record_file.write_text(
        json.dumps({"2024-01-01": "2024-01-01 06:00:00"}), encoding="utf-8"
    )

    records = data.load_sign_records(tmp_path)
    assert sorted((r.task, r.user_id) for r in records) == [
        ("daily", "1001"),
        ("daily", "2002"),
    ]


def test_load_sign_records_survives_corrupt_sqlite_file(tmp_path):
    """data.sqlite3 损坏时退化成「只展示 JSON 记录」，不能把 /api/records 打成 500。"""
    (tmp_path / "data.sqlite3").write_bytes(b"not a sqlite database at all")
    task_dir = tmp_path / "signs" / "daily" / "1001"
    task_dir.mkdir(parents=True)
    (task_dir / "sign_record.json").write_text(
        json.dumps({"2024-01-01": "2024-01-01 06:00:00"}), encoding="utf-8"
    )

    records = data.load_sign_records(tmp_path)
    assert [(r.task, r.user_id) for r in records] == [("daily", "1001")]


# ---------------------------------------------------------------------------
# 日志文件列表：只能列出读得到的那些
# ---------------------------------------------------------------------------


def test_list_log_files_only_lists_paths_the_reader_accepts(tmp_path):
    """列表必须与读取用同一套形状规则（最多一层子目录 + .log）。

    更深一层的文件以前会被列出来，点开却必然 400 —— 「列得出读不到」。
    """
    (tmp_path / "tg-signer.log").write_text("", encoding="utf-8")
    task_dir = tmp_path / "signer-demo"
    task_dir.mkdir()
    (task_dir / "tg-signer.log").write_text("task\n", encoding="utf-8")
    nested = tmp_path / "sub" / "nested"
    nested.mkdir(parents=True)
    deep_log = nested / "x.log"
    deep_log.write_text("deep\n", encoding="utf-8")

    listed = data.list_log_files(tmp_path)
    relative = sorted(str(p.relative_to(tmp_path)).replace("\\", "/") for p in listed)
    assert relative == ["signer-demo/tg-signer.log", "tg-signer.log"]
    assert deep_log.resolve() not in [p.resolve() for p in listed]

    # 列表给出的每个路径都必须能被 reader 接受（往返不 400）。
    for path in listed:
        data.load_logs(limit=10, log_path=path, log_dir=tmp_path)


# ---------------------------------------------------------------------------
# automation YAML：语法错误必须是 ValueError（→ 400），不是 500
# ---------------------------------------------------------------------------


def test_load_automation_config_reports_invalid_yaml_as_value_error(tmp_path):
    pytest.importorskip("yaml")
    auto_dir = tmp_path / "automations" / "broken"
    auto_dir.mkdir(parents=True)
    (auto_dir / "config.yaml").write_text("rules: [\n  - id: x\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML"):
        data.load_automation_config("broken", tmp_path)
