import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from pyrogram.types import Message

from tg_signer.utils import replace_with_retry

if TYPE_CHECKING:
    from tg_signer.core import Client

    from .engine import UserAutomation

# 状态文件「读不了」（被占用/权限不足）时的短暂重试次数与间隔。
# 这类情况几乎都是暂时性的，值得等一下再试，而不是立刻丢数据。
_STATE_READ_RETRIES = 3
_STATE_READ_RETRY_SECONDS = 0.2


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
    # store_state(keys=[...]) 通过它声明「规则结束时只回写这些变量」；
    # None 表示回写全部 ctx.vars（默认契约）。
    persist_vars: Optional[Dict[str, Any]] = None

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
                data = json.load(fp)
            self._validate_shape(data)
        except OSError as exc:
            # 「读不了」和「内容坏了」必须分开处理。
            # PermissionError 是 OSError 子类，而它几乎总是**暂时性**的：
            # 杀软/勒索防护正在扫描、OneDrive/Dropbox 正在按需下载占位文件、
            # 同一任务的另一个 automation 进程正持有句柄、workdir 在网络盘上。
            # 旧实现把它当成损坏：先把真实的 state.json 改名成 .corrupt-<ts>
            # （备份不会自动恢复），再以空状态继续 —— 而下一次 save() 就把空
            # buckets 写回去，用户的计数器/余额/去重键全部不可恢复地丢失，
            # 所有 interval 定时器还会立刻重新触发。
            # 这里改为短暂重试，仍失败就抛出，让用户看到真实原因而不是丢数据。
            for _ in range(_STATE_READ_RETRIES):
                time.sleep(_STATE_READ_RETRY_SECONDS)
                try:
                    with open(self.path, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    self._validate_shape(data)
                    break
                except OSError:
                    continue
            else:
                raise RuntimeError(
                    f"无法读取自动化状态文件（文件被占用或权限不足）: {self.path} ({exc})。"
                    "已保留原文件、未做任何写入；请关闭占用该文件的程序后重试。"
                ) from exc
        except (ValueError, TypeError) as exc:
            # 这里才是真的坏了：JSONDecodeError / UnicodeDecodeError 都是
            # ValueError 子类，形状错误（根不是 dict、rules 不是 dict 等）由
            # _validate_shape 显式抛 ValueError。
            self.logger.warning(
                f"状态文件已损坏: {self.path} ({exc}),已备份为 .corrupt-<ts> 并以空状态继续"
            )
            try:
                backup = self.path.with_name(
                    f"{self.path.name}.corrupt-{int(datetime.now().timestamp())}"
                )
                self.path.replace(backup)
            except OSError as backup_exc:  # noqa: BLE001
                self.logger.warning(f"备份损坏状态文件失败: {backup_exc}")
            self._data = {"rules": {}}
            return
        # 形状合法但缺字段时也要补齐,保证后续访问器永远拿到 {"rules": {...}}。
        data.setdefault("rules", {})
        self._data = data
        self.logger.debug(
            "状态文件加载完成: %s (rules=%s)", self.path, len(self._data["rules"])
        )

    @staticmethod
    def _validate_shape(data: Any) -> None:
        """校验状态文件形状，非法时抛 ``ValueError``。

        形状错误必须在 load 阶段拦住:此前只捕获 JSON 解码错误,``[]`` / ``null``
        / ``{"rules": null}`` 这类文件会让 ``_rule_bucket`` 在**每个**自动化子命令
        上抛 AttributeError/TypeError。
        """
        if not isinstance(data, dict):
            raise ValueError(f"状态文件根节点必须是对象,实际为 {type(data).__name__}")
        rules = data.get("rules", {})
        if not isinstance(rules, dict):
            raise ValueError(
                f"状态文件的 rules 字段必须是对象,实际为 {type(rules).__name__}"
            )
        for rule_id, bucket in rules.items():
            if not isinstance(bucket, dict):
                raise ValueError(f"状态文件 rules.{rule_id} 必须是对象")
            for key in ("vars", "triggers"):
                value = bucket.get(key)
                if value is not None and not isinstance(value, dict):
                    raise ValueError(f"状态文件 rules.{rule_id}.{key} 必须是对象")
            for trigger_id, state in (bucket.get("triggers") or {}).items():
                if not isinstance(state, dict):
                    raise ValueError(
                        f"状态文件 rules.{rule_id}.triggers.{trigger_id} 必须是对象"
                    )
                # 叶子值也必须校验:只查容器的话 {"next_run_at": 1735689600}
                # (手改或旧版本写出)会被当成合法状态放行,随后
                # datetime.fromisoformat(int) 抛的是 TypeError 而不是
                # ValueError,会逃出 get_trigger_next_run 的捕获、每秒打断一次
                # 整个 _tick_timers —— 该配置里所有 timer 规则随之静默停摆。
                for leaf in ("next_run_at", "last_run_at"):
                    value = state.get(leaf)
                    if value is not None and not isinstance(value, str):
                        raise ValueError(
                            f"状态文件 rules.{rule_id}.triggers.{trigger_id}."
                            f"{leaf} 必须是字符串或 null,实际为 "
                            f"{type(value).__name__}"
                        )

    @staticmethod
    def _json_default(value: Any) -> Any:
        """把状态里出现的非 JSON 原生类型降级成可序列化的值。

        ``rule.vars`` 是 ``Dict[str, Any]``，而 ``yaml.safe_load`` 会把
        ``2024-06-01`` 解析成真正的 ``datetime``。这类值直接交给 ``json.dump``
        会抛 ``TypeError: Object of type datetime is not JSON serializable``,
        异常从 ``_run_rule`` 逃出去后 timer 的 next_run_at 不会被推进 ——
        于是一条 ``interval_seconds: 3600`` 的规则会在每个 tick 重新触发,
        实测 0.2 秒内重复发 12 条消息。这里统一降级而不是让整条规则链崩掉。
        """
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (set, frozenset, tuple)):
            return list(value)
        if isinstance(value, Path):
            return str(value)
        return str(value)

    def save(self, force: bool = False) -> None:
        # 无变更时跳过落盘，减少频繁 IO。
        if not self._dirty and not force:
            self.logger.debug("状态未变化，跳过写入: %s", self.path)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 写临时文件再原子替换,避免崩溃/Ctrl-C 中途损坏状态文件。
        # 临时文件名必须唯一：两个 automation 进程/线程操作同一任务目录时，
        # 固定的 state.json.tmp 会让双方共写同一个临时文件 —— 一边以 "w" 截断、
        # 另一边随后 os.replace，就会把一个被截断的 state.json 装上去，下次
        # load 直接判定损坏并清空。Windows 上还会周期性地报 PermissionError。
        tmp_path = self.path.with_name(
            f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            with open(tmp_path, "w", encoding="utf-8") as fp:
                json.dump(
                    self._data,
                    fp,
                    ensure_ascii=False,
                    indent=2,
                    default=self._json_default,
                )
                fp.flush()
                os.fsync(fp.fileno())
            replace_with_retry(tmp_path, self.path, attempts=5, delay=0.05)
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
        # fromisoformat 只接受 str:传进非字符串抛的是 TypeError。必须一并捕获,
        # 否则单个坏 trigger 会让 _tick_timers 每秒炸一次,拖垮同配置的其它规则。
        except (TypeError, ValueError):
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
