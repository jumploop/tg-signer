import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from pyrogram.types import Message

if TYPE_CHECKING:
    from tg_signer.core import Client

    from .engine import UserAutomation


@dataclass
class Event:
    """一次规则执行的输入事件。"""

    type: str
    chat_id: Optional[int | str]
    message: Optional[Message]
    now: datetime
    trigger_id: str
    rule_id: str


@dataclass
class AutomationContext:
    """handler 链共享的运行上下文。"""

    vars: Dict[str, Any]
    state: "RuleStateStore"
    client: "Client"
    logger: logging.Logger
    worker: "UserAutomation"
    workdir: Path

    def log(self, msg: str, level: str = "INFO") -> None:
        normalized_level = level.upper()
        if normalized_level == "ERROR":
            self.logger.error(msg)
        elif normalized_level == "WARNING":
            self.logger.warning(msg)
        elif normalized_level == "CRITICAL":
            self.logger.critical(msg)
        elif normalized_level == "DEBUG":
            self.logger.debug(msg)
        else:
            self.logger.info(msg)


class RuleStateStore:
    """按 rule/trigger 维度持久化自动化运行状态。"""

    def __init__(self, path: Path, logger: logging.Logger) -> None:
        self.path = path
        self.logger = logger
        self._data: Dict[str, Any] = {"rules": {}}
        self._dirty = False
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            self.logger.debug(f"状态文件不存在，使用空状态: {self.path}")
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fp:
                self._data = json.load(fp)
            rules = self._data.get("rules", {})
            self.logger.debug("状态文件加载完成: %s (rules=%s)", self.path, len(rules))
        except (OSError, json.JSONDecodeError) as exc:
            # 损坏时备份原文件,避免下次 save 静默覆盖导致状态彻底丢失
            self.logger.warning(
                f"无法读取状态文件: {self.path} ({exc}),已备份为 .corrupt-<ts> 并以空状态继续"
            )
            try:
                backup = self.path.with_name(
                    f"{self.path.name}.corrupt-{int(datetime.now().timestamp())}"
                )
                self.path.replace(backup)
            except OSError as backup_exc:  # noqa: BLE001
                self.logger.warning(f"备份损坏状态文件失败: {backup_exc}")
            self._data = {"rules": {}}

    def save(self, force: bool = False) -> None:
        # 无变更时跳过落盘，减少频繁 IO。
        if not self._dirty and not force:
            self.logger.debug("状态未变化，跳过写入: %s", self.path)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 写临时文件再原子替换,避免崩溃/Ctrl-C 中途损坏状态文件
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as fp:
                json.dump(self._data, fp, ensure_ascii=False, indent=2)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp_path, self.path)
        finally:
            # 任何异常都清理临时文件,避免残留
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:  # noqa: BLE001
                    pass
        self._dirty = False
        self.logger.debug("状态文件写入完成: %s", self.path)

    def _rule_bucket(self, rule_id: str) -> Dict[str, Any]:
        # 结构：rules.<rule_id>.{vars,triggers}
        rules = self._data.setdefault("rules", {})
        return rules.setdefault(rule_id, {"vars": {}, "triggers": {}})

    def get_rule_vars(self, rule_id: str) -> Dict[str, Any]:
        return dict(self._rule_bucket(rule_id).get("vars") or {})

    def set_rule_vars(self, rule_id: str, vars_value: Dict[str, Any]) -> None:
        bucket = self._rule_bucket(rule_id)
        bucket["vars"] = vars_value
        self._dirty = True

    def get_trigger_state(self, rule_id: str, trigger_id: str) -> Dict[str, Any]:
        bucket = self._rule_bucket(rule_id)
        triggers = bucket.setdefault("triggers", {})
        return triggers.setdefault(trigger_id, {})

    def get_trigger_next_run(self, rule_id: str, trigger_id: str) -> Optional[datetime]:
        state = self.get_trigger_state(rule_id, trigger_id)
        raw = state.get("next_run_at")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def set_trigger_next_run(
        self, rule_id: str, trigger_id: str, dt: Optional[datetime]
    ) -> None:
        state = self.get_trigger_state(rule_id, trigger_id)
        state["next_run_at"] = dt.isoformat() if dt else None
        self._dirty = True

    def set_trigger_last_run(
        self, rule_id: str, trigger_id: str, dt: Optional[datetime]
    ) -> None:
        state = self.get_trigger_state(rule_id, trigger_id)
        state["last_run_at"] = dt.isoformat() if dt else None
        self._dirty = True
