import asyncio
import json
import logging
import random
import re
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple, Union

from croniter import CroniterBadCronError, croniter
from pyrogram import filters
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from pyrogram.methods.utilities.idle import idle
from pyrogram.types import Message

from tg_signer.config import (
    AutomationConfig,
    FilterConfig,
    HandlerConfig,
    MessageTriggerConfig,
    RuleConfig,
    TimerTriggerConfig,
    TriggerConfig,
    normalize_chat_ref,
)
from tg_signer.core import BaseUserWorker, get_now
from tg_signer.utils import safe_regex_search

from .handlers import (
    get_handler,
    list_handlers,
    load_plugins,
    register_builtin_handlers,
)
from .models import AutomationContext, Event, RuleStateStore

logger = logging.getLogger("tg-signer")

# 引擎实际驱动了哪些触发器类型。config 的 `TriggerConfig` 是 discriminated union，
# 未知 type 在解析阶段就会被拒；但如果 config 那边新增了类型而这里没跟上，就会变成
# 「配置合法、规则却永不触发」的静默失效。两边清单的一致性由
# tests/test_automation_engine.py::test_engine_drives_every_declared_trigger_type 兜住。
STARTUP_TRIGGER_TYPE = "startup"
TIMER_TRIGGER_TYPE = "timer"
MESSAGE_TRIGGER_TYPE = "message"
SUPPORTED_TRIGGER_TYPES = frozenset(
    {STARTUP_TRIGGER_TYPE, TIMER_TRIGGER_TYPE, MESSAGE_TRIGGER_TYPE}
)

# 自动化配置文件的候选文件名(JSON 优先,其次 YAML)。集中一处,避免
# 「建目录的解析」与「不建目录的存在性查询」两份清单各自漂移。
CONFIG_FILE_NAMES = ("config.json", "config.yaml", "config.yml")


class UserAutomation(BaseUserWorker[AutomationConfig]):
    """规则驱动的自动化执行器。

    核心流程：
    1) 载入规则配置；
    2) 监听消息事件 + 启动定时循环；
    3) 按规则触发并串行执行 handler 链。
    """

    _workdir = ".signer"
    _tasks_dir = "automations"
    cfg_cls = AutomationConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 状态存储懒加载:仅构造 worker 不应触碰 <workdir>/automations/<task>,
        # 否则 `automation list` 这类只读命令会凭空建出任务目录。
        self._state: Optional[RuleStateStore] = None
        self._tick_seconds = 1.0
        # 按 chat_id -> message_id 缓存最近消息，供后续 wait_for/复杂 handler 复用。
        # 外层也用 OrderedDict:chat 数量同样要能按 LRU 淘汰。
        self._message_cache: "OrderedDict[int, OrderedDict[int, Message]]" = (
            OrderedDict()
        )
        self._message_cache_limit = 200
        # 聊天的数量同样要有上限:只限单聊消息数的话,长期运行会随聊天数无限增长。
        self._message_cache_chats_limit = 64

    def ensure_ctx(self):
        return {}

    @property
    def state(self) -> RuleStateStore:
        if self._state is None:
            self._state = RuleStateStore(self.state_file, logger)
        return self._state

    @state.setter
    def state(self, value: RuleStateStore) -> None:
        self._state = value

    @property
    def state_file(self) -> Path:
        return self.task_dir / "state.json"

    @property
    def handlers_dir(self) -> Path:
        return self.workdir / "handlers"

    @classmethod
    def list_task_names(cls, workdir: Union[str, Path]) -> List[str]:
        """列出已有自动化任务目录名（只读，不创建任何目录）。

        `automation list` 需要一个不构造 worker 的入口:构造 worker 会带上
        默认任务名并据此建目录,把「列出」变成「创建」。
        """
        tasks_dir = Path(workdir) / cls._tasks_dir
        if not tasks_dir.is_dir():
            return []
        return sorted(path.name for path in tasks_dir.iterdir() if path.is_dir())

    def config_dir_path(self) -> Path:
        """任务配置目录路径(只拼路径,不创建目录)。"""
        return self.workdir / self._tasks_dir / self.task_name

    def find_existing_config_file(self) -> Optional[Path]:
        """返回已存在的配置文件;都不存在时返回 ``None``,且不创建任何目录。

        只读命令必须用它而不是 :meth:`_resolve_config_file`:后者经 ``task_dir``
        会 ``make_dirs``,于是 ``automation validate <打错的task>`` 会在磁盘上
        留下一个空的 ``<workdir>/automations/<task>/`` 目录,随后被 ``list``
        当成真实任务列出来。
        """
        task_dir = self.config_dir_path()
        for name in CONFIG_FILE_NAMES:
            candidate = task_dir / name
            if candidate.exists():
                return candidate
        return None

    def _config_candidates(self) -> List[Path]:
        # JSON 优先，其次 YAML，符合当前产品决策。
        return [self.task_dir / name for name in CONFIG_FILE_NAMES]

    def _resolve_config_file(self) -> Path:
        # 返回第一个存在的配置文件；若都不存在，则返回默认 JSON 路径。
        for path in self._config_candidates():
            if path.exists():
                return path
        return self._config_candidates()[0]

    def _read_config_payload(self, path: Path) -> Dict[str, object]:
        if path.suffix in {".yml", ".yaml"}:
            try:
                import yaml  # type: ignore
            except ModuleNotFoundError as exc:
                raise ValueError("未安装pyyaml，无法读取YAML配置") from exc
            with open(path, "r", encoding="utf-8") as fp:
                payload = yaml.safe_load(fp) or {}
            if not isinstance(payload, dict):
                raise ValueError("YAML配置必须是字典结构")
            return payload
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def load_config(
        self, cfg_cls: Optional[type[AutomationConfig]] = None
    ) -> AutomationConfig:  # type: ignore[override]
        cfg_cls = cfg_cls or self.cfg_cls
        config_path = self._resolve_config_file()
        self.log(f"读取自动化配置: {config_path}", level="DEBUG")
        if not config_path.exists():
            self.log("配置文件不存在，生成模板配置", level="INFO")
            config = self.reconfig()
        else:
            payload = self._read_config_payload(config_path)
            config, from_old, err = cfg_cls.load_checked(payload)
            if config is None:
                raise ValueError(f"无法解析配置: {config_path}（{err or '未知原因'}）")
            if config_path.suffix in {".yml", ".yaml"}:
                self.config = config
                self.log(
                    f"配置加载完成: rules={len(config.rules)} (yaml)", level="INFO"
                )
                return config
            if config_path.suffix == ".json" and from_old:
                self.write_config(config)
                self.log("检测到旧版配置并已自动迁移为当前结构", level="INFO")
        self.config = config
        self.log(f"配置加载完成: rules={len(config.rules)}", level="INFO")
        return config

    def export(self):  # type: ignore[override]
        config_path = self._resolve_config_file()
        if not config_path.exists():
            raise FileNotFoundError(f"配置不存在: {config_path}")
        with open(config_path, "r", encoding="utf-8") as fp:
            return fp.read()

    def _parse_import_payload(self, config_str: str) -> Dict[str, object]:
        # 导入内容可能是 JSON,也可能是从 YAML 任务导出的 YAML 文本。
        try:
            payload = json.loads(config_str)
        except ValueError:
            try:
                import yaml  # type: ignore
            except ModuleNotFoundError as exc:
                raise ValueError(
                    "导入内容不是合法JSON，且未安装pyyaml无法按YAML解析"
                ) from exc
            try:
                payload = yaml.safe_load(config_str)
            except yaml.YAMLError as exc:
                raise ValueError(f"无法解析导入内容: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("导入内容必须是JSON/YAML对象")
        return payload

    def _write_config_payload(self, path: Path, config: AutomationConfig) -> None:
        payload = config.to_jsonable()
        if path.suffix in {".yml", ".yaml"}:
            try:
                import yaml  # type: ignore
            except ModuleNotFoundError as exc:
                raise ValueError("未安装pyyaml，无法写入YAML配置") from exc
            with open(path, "w", encoding="utf-8") as fp:
                yaml.safe_dump(payload, fp, allow_unicode=True, sort_keys=False)
            return
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False)

    def import_(self, config_str: str) -> None:  # type: ignore[override]
        """按目标文件格式落盘。

        `export()` 导出的是解析后配置文件(可能是 YAML)的原文,而基类实现一律写
        `<task>/config.json`:YAML 文本落进 config.json 后会遮蔽 config.yaml 并
        解析失败。这里先解析(JSON 优先、YAML 兜底)、校验,再按目标文件格式序列化。
        """
        target = self._resolve_config_file()
        payload = self._parse_import_payload(config_str)
        config, _from_old, err = self.cfg_cls.load_checked(payload)
        if config is None:
            raise ValueError(f"无法解析导入配置（{err or '未知原因'}）")
        self._write_config_payload(target, config)
        self.config = config
        self.log(f"配置已导入: {target}", level="INFO")

    def ask_for_config(self) -> AutomationConfig:
        return self.template_config()

    def template_config(self) -> AutomationConfig:
        return AutomationConfig(
            rules=[
                RuleConfig(
                    id="demo_message_reply",
                    enabled=True,
                    triggers=[
                        MessageTriggerConfig(
                            type="message",
                            params={
                                "chat_id": "@channel_or_user",
                                "from_user_ids": None,
                                "reply_to_me": False,
                            },
                        )
                    ],
                    filters=FilterConfig(
                        text_rule="contains",
                        text_value="关键词",
                        ignore_case=True,
                    ),
                    handlers=[
                        HandlerConfig(
                            handler="send_text",
                            params={"text": "自动回复"},
                        )
                    ],
                    vars={},
                )
            ]
        )

    async def run(
        self,
        num_of_dialogs: int = 20,
        folder: Optional[str] = None,
    ):
        if self.user is None:
            await self.login(num_of_dialogs, print_chat=True, folder=folder)

        cfg = self.load_config(self.cfg_cls)
        if cfg.requires_ai:
            self.ensure_ai_cfg()

        register_builtin_handlers()
        load_plugins(self.handlers_dir, logger)
        self.log(f"已注册 handlers 数量: {len(list(list_handlers()))}", level="INFO")

        self.app.add_handler(MessageHandler(self.on_message, filters.all))
        self.app.add_handler(EditedMessageHandler(self.on_edited_message, filters.all))
        # 后台任务必须在 client 真正启动之后创建:冷启动时 client 还没 start,
        # 首次 Telegram 调用会抛 "Client has not been started yet",该异常会被
        # `_run_rule` 吞掉并中断 handler 链,timer 的 next_run_at 还会被照常推进
        # —— 即本次到期的运行被静默消费。
        startup_tasks: List[asyncio.Task] = []
        timer_task: Optional[asyncio.Task] = None
        async with self.app:
            # startup trigger 每条规则只在进程启动后执行一次。
            startup_tasks = [
                asyncio.create_task(self.run_startup(rule))
                for rule in cfg.rules
                if rule.enabled and self._has_trigger(rule, STARTUP_TRIGGER_TYPE)
            ]
            self.log(f"startup 任务数: {len(startup_tasks)}", level="DEBUG")
            # timer trigger 统一由轮询调度循环驱动。
            timer_task = asyncio.create_task(self.timer_loop())
            for task in (*startup_tasks, timer_task):
                task.add_done_callback(self._log_task_failure)
            self.log("开始自动化运行...")
            try:
                await idle()
            finally:
                # 退出前取消后台任务:此时 client 仍在运行,取消是安全的。
                for task in startup_tasks:
                    task.cancel()
                timer_task.cancel()

    def _has_trigger(self, rule: RuleConfig, trigger_type: str) -> bool:
        return any(trigger.type == trigger_type for trigger in rule.triggers)

    @staticmethod
    def _iter_triggers(
        rule: RuleConfig, trigger_type: str
    ) -> Iterator[Tuple[int, TriggerConfig]]:
        """按类型取出规则下的触发器，连同下标一起给出（`_trigger_id` 需要它）。

        三条驱动路径都必须按类型筛选，收敛到这一处，避免每个循环各写一遍
        `trigger.type != "..."` 而漏掉某个分支。
        """
        for index, trigger in enumerate(rule.triggers):
            if trigger.type == trigger_type:
                yield index, trigger

    @staticmethod
    def _log_task_failure(task: asyncio.Task) -> None:
        """记录后台任务异常退出。

        这些协程没有 await 点,不主动取异常的话只会以
        "Task exception was never retrieved" 的形式被 GC 打印,故障会被静默吞掉。
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("后台任务异常退出: %s", exc, exc_info=exc)

    async def run_startup(self, rule: RuleConfig) -> None:
        for index, trigger in self._iter_triggers(rule, STARTUP_TRIGGER_TYPE):
            trigger_params = trigger.params
            trigger_id = self._trigger_id(rule, trigger, index)
            self.log(
                f"执行 startup 触发: rule={rule.id}, trigger={trigger_id}",
                level="DEBUG",
            )
            event = Event(
                type="startup",
                chat_id=trigger_params.chat_id,
                message=None,
                now=get_now(),
                trigger_id=trigger_id,
                rule_id=rule.id,
            )
            await self._run_rule(rule, event)

    async def timer_loop(self) -> None:
        """轮询调度循环。

        异常必须被关在这一层:该协程是 ``create_task`` 起的、无人 await,
        一旦抛出就只会以 "Task exception was never retrieved" 的形式被 GC
        打印,进程照常存活但**所有 timer 规则永久不再触发**(静默失效)。
        """
        self.log(f"timer 轮询启动, tick={self._tick_seconds}s", level="DEBUG")
        while True:
            try:
                await self._tick_timers()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("timer 轮询异常，%ss 后继续", self._tick_seconds)
            await asyncio.sleep(self._tick_seconds)

    async def _tick_timers(self) -> None:
        """遍历所有 timer trigger,到期即执行一轮规则。"""
        now = get_now()
        cfg = self.config
        for rule in cfg.rules:
            if not rule.enabled:
                continue
            for index, timer_trigger in self._iter_triggers(rule, TIMER_TRIGGER_TYPE):
                trigger_id = self._trigger_id(rule, timer_trigger, index)
                next_run = self.state.get_trigger_next_run(rule.id, trigger_id)
                if next_run is None:
                    # 首次见到该 trigger，计算并写入 next_run_at。
                    next_run = self._compute_next_run(timer_trigger, now)
                    if next_run:
                        self.state.set_trigger_next_run(rule.id, trigger_id, next_run)
                        self.state.save()
                        self.log(
                            f"初始化 timer 下次执行: rule={rule.id}, trigger={trigger_id}, next={next_run.isoformat()}",
                            level="DEBUG",
                        )
                    else:
                        self.log(
                            f"timer 未配置 cron/interval: rule={rule.id}, trigger={trigger_id}",
                            level="DEBUG",
                        )
                    continue
                if now >= next_run:
                    self.log(
                        f"触发 timer: rule={rule.id}, trigger={trigger_id}, due={next_run.isoformat()}",
                        level="DEBUG",
                    )
                    event = Event(
                        type="timer",
                        chat_id=timer_trigger.params.chat_id,
                        message=None,
                        now=now,
                        trigger_id=trigger_id,
                        rule_id=rule.id,
                    )
                    await self._run_rule(rule, event)
                    next_run = self.state.get_trigger_next_run(rule.id, trigger_id)
                    if not next_run or next_run <= now:
                        # 未被 schedule_next 覆盖时，按 trigger 默认策略推导下一次。
                        next_run = self._compute_next_run(timer_trigger, now)
                    self.state.set_trigger_next_run(rule.id, trigger_id, next_run)
                    self.state.set_trigger_last_run(rule.id, trigger_id, now)
                    self.state.save()
                    self.log(
                        f"timer 执行完成: rule={rule.id}, trigger={trigger_id}, next={next_run.isoformat() if next_run else 'None'}",
                        level="DEBUG",
                    )

    async def on_message(self, client, message: Message):
        _ = client
        await self._handle_message_event(message, event_type="message")

    async def on_edited_message(self, client, message: Message):
        _ = client
        await self._handle_message_event(message, event_type="edited_message")

    async def _handle_message_event(self, message: Message, event_type: str) -> None:
        # 消息/编辑消息统一走“触发器匹配 -> 过滤器匹配 -> handler链”三段式流程。
        self._cache_message(message)
        cfg = self.config
        for rule in cfg.rules:
            if not rule.enabled:
                continue
            for index, trigger in self._iter_triggers(rule, MESSAGE_TRIGGER_TYPE):
                if not self._match_message_trigger(trigger, message):
                    continue
                if rule.filters and not self._match_filter(rule.filters, message):
                    continue
                trigger_id = self._trigger_id(rule, trigger, index)
                self.log(
                    f"{event_type}命中规则: rule={rule.id}, trigger={trigger_id}, chat={message.chat.id}",
                    level="DEBUG",
                )
                event = Event(
                    type=event_type,
                    chat_id=message.chat.id,
                    message=message,
                    now=get_now(),
                    trigger_id=trigger_id,
                    rule_id=rule.id,
                )
                await self._run_rule(rule, event)

    def _cache_message(self, message: Message) -> None:
        message_id = message.id
        chat_id = message.chat and message.chat.id
        if chat_id is None:
            return
        cache = self._message_cache.setdefault(chat_id, OrderedDict())
        # 同时把 chat 自身标记为最近使用,超出上限时按 LRU 淘汰整个 chat。
        self._message_cache.move_to_end(chat_id)
        cache[message_id] = message
        cache.move_to_end(message_id)
        while len(cache) > self._message_cache_limit:
            cache.popitem(last=False)
        while len(self._message_cache) > self._message_cache_chats_limit:
            self._message_cache.popitem(last=False)
        self.log(
            f"消息已缓存: chat={chat_id}, message_id={message_id}, cached={len(cache)}",
            level="DEBUG",
        )

    def get_cached_messages(
        self, chat_id: int, limit: Optional[int] = None
    ) -> List[Message]:
        cache = self._message_cache.get(chat_id)
        if not cache:
            return []
        messages = list(cache.values())
        if limit is None or limit <= 0:
            return messages
        return messages[-limit:]

    def _trigger_id(self, rule: RuleConfig, trigger: TriggerConfig, index: int) -> str:
        return trigger.id or f"{rule.id}:{index}"

    def _compute_next_run(
        self, trigger: TimerTriggerConfig, now: datetime
    ) -> Optional[datetime]:
        # timer 支持 cron 或固定间隔，二选一。
        trigger_params = trigger.params
        if trigger_params.cron:
            try:
                it = croniter(trigger_params.cron, start_time=now)
                next_dt: datetime = it.next(ret_type=datetime)
            except CroniterBadCronError:
                self.log(f"cron表达式无效: {trigger_params.cron}", level="WARNING")
                return None
        elif trigger_params.interval_seconds:
            next_dt = now + timedelta(seconds=trigger_params.interval_seconds)
        else:
            return None
        if trigger_params.random_seconds:
            next_dt += timedelta(
                seconds=random.randint(0, trigger_params.random_seconds)
            )
        self.log(
            f"计算下次 timer: cron={trigger_params.cron}, interval={trigger_params.interval_seconds}, next={next_dt.isoformat()}",
            level="DEBUG",
        )
        return next_dt

    def _match_message_trigger(
        self, trigger: MessageTriggerConfig, message: Message
    ) -> bool:
        trigger_params = trigger.params
        if trigger_params.chat_id or trigger_params.chat_ids:
            if not self._match_chat(
                message,
                trigger_params.chat_id,
                trigger_params.chat_ids,
                ignore_case=trigger_params.ignore_case,
            ):
                return False
        if trigger_params.from_user_ids:
            if not self._match_user(message, trigger_params.from_user_ids):
                return False
        if trigger_params.reply_to_me:
            if not message.reply_to_message:
                return False
            if not message.reply_to_message.from_user:
                return False
            if not message.reply_to_message.from_user.is_self:
                return False
        if trigger_params.reply_to_message_id:
            if not message.reply_to_message:
                return False
            if message.reply_to_message.id != trigger_params.reply_to_message_id:
                return False
        return True

    def _match_filter(self, filter_cfg: FilterConfig, message: Message) -> bool:
        if filter_cfg.chat_id or filter_cfg.chat_ids:
            if not self._match_chat(
                message,
                filter_cfg.chat_id,
                filter_cfg.chat_ids,
                ignore_case=filter_cfg.ignore_case,
            ):
                return False
        if filter_cfg.from_user_ids:
            if not self._match_user(message, filter_cfg.from_user_ids):
                return False
        text = message.text or message.caption or ""
        rule = filter_cfg.text_rule
        value = filter_cfg.text_value or ""
        if rule != "all" and not value:
            return False
        if rule == "all":
            return True
        if rule == "exact":
            if filter_cfg.ignore_case:
                return text.lower() == value.lower()
            return text == value
        if rule == "contains":
            if filter_cfg.ignore_case:
                return value.lower() in text.lower()
            return value in text
        if rule == "regex":
            flags = 0 if not filter_cfg.ignore_case else re.IGNORECASE
            try:
                return safe_regex_search(value, text, flags=flags) is not None
            except ValueError as exc:
                # 配置里的正则非法/超长:当成「不匹配」而不是抛异常打断整条规则链。
                self.log(f"filters.text_rule: {exc}", level="WARNING")
                return False
        return False

    def _match_user(
        self, message: Message, from_user_ids: Iterable[Union[int, str]]
    ) -> bool:
        # 无发送者（频道帖、服务消息等）无法判定是否来自指定用户，不应放行。
        if not message.from_user:
            return False
        normalized = {
            self._normalize_user_id(item) for item in from_user_ids if item is not None
        }
        user_id = message.from_user.id
        username = message.from_user.username
        if user_id in normalized:
            return True
        if username and username.lower().strip("@") in normalized:
            return True
        if "me" in normalized and message.from_user.is_self:
            return True
        return False

    def _normalize_user_id(self, value: Union[int, str]) -> Union[int, str]:
        if isinstance(value, str):
            if value in {"me", "self"}:
                return "me"
            text = value.lower().strip("@")
            # 数字字符串也要能匹配 int 形式的 user id。
            return normalize_chat_ref(text)
        return value

    def _match_chat(
        self,
        message: Message,
        chat_id: Optional[Union[int, str]],
        chat_ids: Optional[List[Union[int, str]]],
        ignore_case: bool = True,
    ) -> bool:
        if chat_ids is None:
            chat_ids = []
        if chat_id is not None:
            chat_ids = list(chat_ids) + [chat_id]
        if not chat_ids:
            return True
        for target in chat_ids:
            # 配置里写成数字字符串也要能命中，否则规则会静默永不触发。
            target = normalize_chat_ref(target)
            if isinstance(target, int) and message.chat.id == target:
                return True
            if isinstance(target, str):
                # Telegram 用户名大小写不敏感:`@MyChannel` 与配置里的
                # `@mychannel` 必须能互相命中(ignore_case 默认 True)。
                target_norm = target.strip("@")
                username = (message.chat.username or "").strip("@")
                if ignore_case:
                    if username.lower() == target_norm.lower():
                        return True
                elif username == target_norm:
                    return True
        return False

    async def _run_rule(self, rule: RuleConfig, event: Event) -> None:
        # 规则级变量 = 配置初始变量 + 持久化状态变量（后者覆盖前者）。
        ctx_vars = {**rule.vars, **self.state.get_rule_vars(rule.id)}
        self.log(
            f"开始执行规则: rule={rule.id}, trigger={event.trigger_id}, type={event.type}",
            level="DEBUG",
        )
        ctx = AutomationContext(
            vars=ctx_vars,
            state=self.state,
            client=self.app,
            logger=logger,
            worker=self,
            workdir=self.workdir,
        )
        for handler_cfg in rule.handlers:
            handler = get_handler(handler_cfg.handler)
            if not handler:
                self.log(f"未找到handler: {handler_cfg.handler}", level="WARNING")
                break
            try:
                self.log(
                    f"执行 handler: rule={rule.id}, handler={handler_cfg.handler}",
                    level="DEBUG",
                )
                result = await handler(event, ctx, handler_cfg.params or {})
                self.log(
                    f"handler 结果: rule={rule.id}, handler={handler_cfg.handler}, result={result}",
                    level="DEBUG",
                )
            except Exception as exc:  # noqa: BLE001
                self.log(
                    f"handler执行失败: {handler_cfg.handler} ({exc})", level="ERROR"
                )
                break
            if result in {"stop", "defer"}:
                # stop/defer 都会中断后续 handler。
                break
        # store_state(keys=[...]) 可用 ctx.persist_vars 限定只回写部分变量;
        # 未声明时维持原契约:回写全部 ctx.vars。
        persisted_vars = ctx.persist_vars if ctx.persist_vars is not None else ctx.vars
        self.state.set_rule_vars(rule.id, persisted_vars)
        self.state.save()
        self.log(
            f"规则执行结束并持久化变量: rule={rule.id}, keys={list(persisted_vars.keys())}",
            level="DEBUG",
        )
