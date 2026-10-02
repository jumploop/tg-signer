"""``tg_signer.automation.models`` 的回归测试。

本文件覆盖 ``RuleStateStore`` 的状态文件读写路径 —— 它是自动化引擎唯一的
持久化载体，读错一次就意味着用户计数器/去重键/定时器进度不可恢复地丢失。
"""

import builtins
import json
import logging
import os
import threading
from pathlib import Path

import pytest

from tg_signer.automation.models import RuleStateStore

_LOGGER = logging.getLogger("test_rule_state_store")


def _state_path(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


def _corrupt_backups(tmp_path: Path):
    return sorted(p.name for p in tmp_path.glob("state.json.corrupt-*"))


# ---------------------------------------------------------------------------
# load()：「读不了」不等于「内容坏了」
# ---------------------------------------------------------------------------


def test_load_oserror_raises_and_keeps_the_real_file(tmp_path, monkeypatch):
    """``PermissionError`` 必须抛出并**保留原文件**，不能当成损坏处理。

    回归：旧实现把 ``OSError`` 与「内容损坏」混为一谈 —— 先把真实的
    ``state.json`` 改名成 ``.corrupt-<ts>``（备份不会自动恢复），再以空状态
    继续；下一次 ``save()`` 就把空 buckets 写回去，计数器、去重键、余额全部
    丢失，而且所有 ``interval`` 定时器会立刻重新触发。
    ``PermissionError`` 几乎总是暂时性的（杀软扫描、云盘按需下载、另一个
    进程正持有句柄），把它当损坏处理等于把一次瞬时抖动变成数据丢失。
    """
    path = _state_path(tmp_path)
    real_content = {"rules": {"r1": {"vars": {"counter": 42}}}}
    path.write_text(json.dumps(real_content), encoding="utf-8")

    real_open = builtins.open

    def _boom(file, *args, **kwargs):
        if Path(file) == path:
            raise PermissionError(13, "used by another process")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _boom)
    # 缩短重试，别让测试真的睡 3 次
    monkeypatch.setattr("tg_signer.automation.models._STATE_READ_RETRIES", 2)
    monkeypatch.setattr("tg_signer.automation.models._STATE_READ_RETRY_SECONDS", 0)

    with pytest.raises(RuntimeError, match="无法读取自动化状态文件"):
        RuleStateStore(path, _LOGGER)

    # 关键：原文件原封不动，备份一个都没造
    assert path.is_file(), "真实的 state.json 被改名/删除了"
    assert json.loads(path.read_text(encoding="utf-8")) == real_content
    assert _corrupt_backups(tmp_path) == []


def test_load_oserror_recovers_when_read_succeeds_on_retry(tmp_path, monkeypatch):
    """第一次读被占用、重试成功后应正常加载，而不是丢数据。"""
    path = _state_path(tmp_path)
    real_content = {"rules": {"r1": {"vars": {"counter": 7}}}}
    path.write_text(json.dumps(real_content), encoding="utf-8")

    real_open = builtins.open
    calls = {"n": 0}

    def _flaky(file, *args, **kwargs):
        if Path(file) == path:
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError(13, "busy")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _flaky)
    monkeypatch.setattr("tg_signer.automation.models._STATE_READ_RETRIES", 3)
    monkeypatch.setattr("tg_signer.automation.models._STATE_READ_RETRY_SECONDS", 0)

    store = RuleStateStore(path, _LOGGER)

    assert store.get_rule_vars("r1") == {"counter": 7}
    assert _corrupt_backups(tmp_path) == []


def test_load_real_corruption_still_backs_up(tmp_path):
    """真正的 JSON 损坏仍然要备份并以空状态继续（防止修过头）。"""
    path = _state_path(tmp_path)
    path.write_text("{not json at all", encoding="utf-8")

    store = RuleStateStore(path, _LOGGER)

    assert store.get_rule_vars("r1") == {}
    assert len(_corrupt_backups(tmp_path)) == 1, "损坏文件没有被备份"


# ---------------------------------------------------------------------------
# save()：临时文件名不能是固定的
# ---------------------------------------------------------------------------


def test_save_uses_unique_tempfile_names(tmp_path, monkeypatch):
    """``state.json.tmp`` 固定名会互相覆盖，临时名必须带 pid + 线程 id。

    回归：两个进程/线程写同一个任务目录时共用 ``state.json.tmp``，一边截断、
    另一边随后 ``os.replace``，会把一个被截断的 ``state.json`` 装上去
    （下次 load 直接判损坏并清空）；Windows 上还表现为周期性
    ``PermissionError``。
    """
    path = _state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    store = RuleStateStore(path, _LOGGER)

    seen = []
    real_replace = os.replace

    def _spy(src, dst):
        seen.append(Path(src))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _spy)

    store.set_rule_vars("r1", {"a": 1})
    store.save(force=True)

    assert seen, "save() 没有经过临时文件 + rename 的原子路径"
    assert seen[0].name != "state.json.tmp", "临时文件名是固定的，多方会互相覆盖"
    assert seen[0].name.endswith(".tmp")
    assert str(seen[0].parent) == str(path.parent), "临时文件与目标不在同一目录"
    assert json.loads(path.read_text(encoding="utf-8"))["rules"]["r1"]["vars"] == {
        "a": 1
    }


def test_concurrent_saves_on_same_path_do_not_corrupt_state(tmp_path):
    """多线程并发 save 到同一路径，最终文件必须是可解析的完整 JSON。"""
    path = _state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    RuleStateStore(path, _LOGGER)  # 初始化 schema

    errors = []
    barrier = threading.Barrier(8)

    def _writer(index):
        store = RuleStateStore(path, _LOGGER)
        try:
            barrier.wait(timeout=5)
            for i in range(20):
                store.set_rule_vars(f"r{index}", {"n": i})
                store.save(force=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"并发保存抛异常: {errors}"
    # 最终文件必须是合法 JSON（被截断过的 JSON 会在这里 JSONDecodeError）
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data["rules"], dict)
    assert list(tmp_path.glob("*.tmp")) == [], "残留了临时文件"


def test_failed_save_leaves_previous_state_and_no_tempfile(tmp_path, monkeypatch):
    """写临时文件失败时，原 state.json 必须完好且不残留临时文件。"""
    path = _state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    store = RuleStateStore(path, _LOGGER)
    store.set_rule_vars("r1", {"counter": 1})
    store.save(force=True)
    before = path.read_text(encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("tg_signer.automation.models.os.replace", _boom)
    store.set_rule_vars("r1", {"counter": 2})
    with pytest.raises(OSError):
        store.save(force=True)

    assert path.read_text(encoding="utf-8") == before, "写失败把已有状态弄坏了"
    assert list(tmp_path.glob("*.tmp")) == [], "失败后残留临时文件"
