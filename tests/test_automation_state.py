import logging
from datetime import datetime, timezone

from tg_signer.automation.models import RuleStateStore


def test_rule_state_store_roundtrip(tmp_path):
    """状态文件写入后应能按 rule/trigger 维度完整回读。"""
    path = tmp_path / "state.json"
    store = RuleStateStore(path, logging.getLogger("test"))
    dt = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    store.set_rule_vars("r1", {"a": 1})
    store.set_trigger_next_run("r1", "t1", dt)
    store.save(force=True)

    store2 = RuleStateStore(path, logging.getLogger("test"))
    assert store2.get_rule_vars("r1")["a"] == 1
    assert store2.get_trigger_next_run("r1", "t1") == dt


def test_rule_state_store_save_uses_temp_file(tmp_path):
    """save() 应使用临时文件 + os.replace 原子写入,不应残留 .tmp。"""
    path = tmp_path / "state.json"
    store = RuleStateStore(path, logging.getLogger("test"))

    store.set_rule_vars("r1", {"a": 1})
    store.save(force=True)

    # 主文件存在且内容合法
    assert path.is_file()
    # 不应残留临时文件
    assert not (path.with_name(path.name + ".tmp")).exists()


def test_rule_state_store_load_corrupt_backs_up_and_continues(tmp_path):
    """load() 遇到损坏 JSON 时应备份原文件并以空状态继续,不抛异常。"""
    path = tmp_path / "state.json"
    path.write_text("{not valid json", encoding="utf-8")

    store = RuleStateStore(path, logging.getLogger("test"))

    # 损坏文件应被备份
    backups = list(path.parent.glob(path.name + ".corrupt-*"))
    assert len(backups) == 1
    assert not path.exists()
    # 以空状态继续
    assert store.get_rule_vars("r1") == {}
    # 下次 save 应写新内容,不会因为旧文件已被备份而失败
    store.set_rule_vars("r1", {"a": 1})
    store.save(force=True)
    assert path.is_file()


def test_rule_state_store_dirty_skip_save(tmp_path):
    """无变更时 save() 应跳过 IO, 不创建临时文件。"""
    path = tmp_path / "state.json"
    store = RuleStateStore(path, logging.getLogger("test"))
    # 初始时 _dirty=False,save 不应写盘
    store.save()
    assert not path.exists()
    assert not (path.with_name(path.name + ".tmp")).exists()
