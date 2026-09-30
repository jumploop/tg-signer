import asyncio
import contextlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import get_args

import pytest
from pydantic import ValidationError

from tg_signer.automation.engine import (
    MESSAGE_TRIGGER_TYPE,
    STARTUP_TRIGGER_TYPE,
    SUPPORTED_TRIGGER_TYPES,
    TIMER_TRIGGER_TYPE,
    UserAutomation,
)
from tg_signer.automation.handlers import register_builtin_handlers
from tg_signer.automation.models import Event, RuleStateStore
from tg_signer.config import (
    AutomationConfig,
    FilterConfig,
    HandlerConfig,
    MessageTriggerConfig,
    RuleConfig,
    StartupTriggerConfig,
    TimerTriggerConfig,
    TriggerConfig,
)


class AutomationHarness(UserAutomation):
    """测试专用实例，避免触发真实 client 初始化与网络依赖。"""

    def __init__(self, tmp_path):
        import logging
        from collections import OrderedDict

        self.task_name = "t"
        self._account = "test_account"
        self._workdir = tmp_path
        self._tasks_dir = "automations"
        self.logger = logging.getLogger("tg-signer")
        _ = self.task_dir  # 触发目录创建
        self._state = None
        self.state = RuleStateStore(self.task_dir / "state.json", self.logger)
        self._tick_seconds = 1.0
        self._message_cache = OrderedDict()
        self._message_cache_limit = 200
        self._message_cache_chats_limit = 64
        self.app = SimpleNamespace(forward_messages=lambda *args, **kwargs: None)


@dataclass
class DummyUser:
    """Message.from_user 的最小替身。"""

    id: int
    username: str | None = None
    is_self: bool = False


@dataclass
class DummyChat:
    """Message.chat 的最小替身。"""

    id: int
    username: str | None = None


@dataclass
class DummyMessage:
    """Message 的最小替身，用于触发/过滤逻辑测试。"""

    text: str | None
    chat: DummyChat
    id: int = 0
    from_user: DummyUser | None = None
    caption: str | None = None
    reply_to_message: "DummyMessage | None" = None


def make_worker(tmp_path):
    """构造 UserAutomation 的测试替身。"""
    return AutomationHarness(tmp_path)


def test_load_config_error_mentions_field(tmp_path):
    """坏 automation 配置要报出字段明细。"""
    worker = make_worker(tmp_path)
    (worker.task_dir / "config.json").write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "r1",
                        "triggers": [
                            {"type": "message", "params": {"chat_id": 1, "nope": 2}}
                        ],
                        "handlers": [{"handler": "send_text", "params": {}}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"params\.nope"):
        worker.load_config()


def test_numeric_string_chat_id_actually_matches(tmp_path):
    """配置里写成字符串数字时，规则也必须能命中（否则静默永不触发）。"""
    worker = make_worker(tmp_path)
    msg = DummyMessage(text="Hello", chat=DummyChat(id=-1001234567890))
    assert worker._match_chat(msg, "-1001234567890", None)


def test_username_chat_id_still_matches_by_username(tmp_path):
    worker = make_worker(tmp_path)
    msg = DummyMessage(text="Hello", chat=DummyChat(id=1, username="neo"))
    assert worker._match_chat(msg, "@neo", None)
    assert not worker._match_chat(msg, "@other", None)


def test_numeric_string_from_user_id_actually_matches(tmp_path):
    worker = make_worker(tmp_path)
    msg = DummyMessage(text="hi", chat=DummyChat(id=1), from_user=DummyUser(id=12345))
    assert worker._match_user(msg, ["12345"])
    assert not worker._match_user(msg, ["999"])


def test_match_filter_variants(tmp_path):
    worker = make_worker(tmp_path)
    chat = DummyChat(id=1, username="room")
    user = DummyUser(id=2, username="Neo", is_self=False)
    msg = DummyMessage(text="Hello World", chat=chat, from_user=user)

    assert worker._match_filter(
        FilterConfig(text_rule="contains", text_value="world", ignore_case=True),
        msg,
    )
    assert worker._match_filter(
        FilterConfig(text_rule="exact", text_value="Hello World", ignore_case=True),
        msg,
    )
    assert not worker._match_filter(
        FilterConfig(text_rule="exact", text_value="hello", ignore_case=False),
        msg,
    )
    assert worker._match_filter(
        FilterConfig(text_rule="regex", text_value=r"Hello\s+World"),
        msg,
    )
    assert worker._match_filter(FilterConfig(text_rule="all"), msg)
    assert not worker._match_filter(
        FilterConfig(text_rule="contains", text_value=""), msg
    )


def test_match_filter_invalid_regex_does_not_break_rule_chain(tmp_path):
    """非法正则只应被判为「不匹配」，不能抛异常打断整条规则链。"""
    worker = make_worker(tmp_path)
    msg = DummyMessage(text="Hello World", chat=DummyChat(id=1))

    # 修复前：re.error 直接冒泡出 _match_filter；修复后：捕获并返回 False。
    assert not worker._match_filter(
        FilterConfig(text_rule="regex", text_value="("), msg
    )


def test_match_filter_catastrophic_regex_is_rejected_fast(tmp_path):
    """灾难性回溯正则应被形态检查拦下，而不是把事件循环卡住若干秒。"""
    worker = make_worker(tmp_path)
    # 24 个 a 后跟非匹配字符：朴素 re.search(r"(a+)+$", ...) 需约 2s。
    msg = DummyMessage(text="a" * 24 + "!", chat=DummyChat(id=1))

    started = time.monotonic()
    matched = worker._match_filter(
        FilterConfig(text_rule="regex", text_value=r"(a+)+$"), msg
    )
    elapsed = time.monotonic() - started

    assert matched is False
    assert elapsed < 1.0, f"正则护栏未生效，耗时 {elapsed:.3f}s"


def test_match_filter_oversized_regex_is_rejected(tmp_path):
    """超长 pattern 应被整体拒绝，即使它本来能匹配。

    这里刻意构造一个「前 12 字符就足以命中、但总长超过 512」的正则：
    没有长度护栏时会返回 True（并可能付出长耗时回溯），加了护栏后必须为 False。
    """
    worker = make_worker(tmp_path)
    msg = DummyMessage(text="Hello World", chat=DummyChat(id=1))
    huge = "Hello World|" + "z" * 510
    assert len(huge) > 512

    assert not worker._match_filter(
        FilterConfig(text_rule="regex", text_value=huge), msg
    )


def test_match_filter_caps_regex_subject_length(tmp_path):
    """超长正文按上限截断后匹配：上限内命中、上限外不命中。"""
    worker = make_worker(tmp_path)
    pattern = FilterConfig(text_rule="regex", text_value="NEEDLE")

    # 关键词在上限内 → 命中。
    assert worker._match_filter(
        pattern, DummyMessage(text="NEEDLE" + "x" * 9000, chat=DummyChat(id=1))
    )
    # 关键词被推到上限之外（8KB 之后）→ 截断后不再命中，避免无上限的回溯开销。
    assert not worker._match_filter(
        pattern, DummyMessage(text="x" * 9000 + "NEEDLE", chat=DummyChat(id=1))
    )


def test_match_message_trigger_and_user(tmp_path):
    worker = make_worker(tmp_path)
    chat = DummyChat(id=1, username="room")
    me = DummyUser(id=99, username="me", is_self=True)
    other = DummyUser(id=2, username="neo", is_self=False)
    replied = DummyMessage(text="hi", chat=chat, from_user=me)
    msg = DummyMessage(text="ok", chat=chat, from_user=other, reply_to_message=replied)

    trigger = MessageTriggerConfig(
        type="message", params={"chat_id": 1, "reply_to_me": True}
    )
    assert worker._match_message_trigger(trigger, msg)

    trigger = MessageTriggerConfig(type="message", params={"from_user_ids": ["neo", 2]})
    assert worker._match_message_trigger(trigger, msg)

    trigger = MessageTriggerConfig(type="message", params={"from_user_ids": ["me"]})
    assert not worker._match_message_trigger(trigger, msg)

    # 无发送者的消息（频道帖/服务消息）不应命中任何 from_user_ids 过滤。
    anonymous = DummyMessage(text="post", chat=chat, from_user=None)
    trigger = MessageTriggerConfig(
        type="message", params={"from_user_ids": ["neo", "me"]}
    )
    assert not worker._match_user(anonymous, ["neo", "me"])
    assert not worker._match_message_trigger(trigger, anonymous)


def test_match_chat_ids_and_username(tmp_path):
    worker = make_worker(tmp_path)
    chat = DummyChat(id=1, username="room")
    msg = DummyMessage(text="ok", chat=chat)

    assert worker._match_chat(msg, 1, None)
    assert worker._match_chat(msg, "@room", None)
    assert worker._match_chat(msg, None, ["@room", 2])
    assert not worker._match_chat(msg, None, ["@other"])


def test_numeric_chat_id_written_as_string_never_matches(tmp_path):
    """WebUI 复制到配置必须把数字 ID 写成 JSON 数字而非字符串。

    ``_match_chat`` 只对 ``int`` 做数字比较，字符串 "-1001234567890" 会落进
    ``@username`` 分支，与任何数字群都对不上，规则会静默失效。
    """
    worker = make_worker(tmp_path)
    chat = DummyChat(id=-1001234567890, username="my_channel")
    msg = DummyMessage(text="ok", chat=chat)

    payload = {
        "rules": [
            {
                "id": "demo",
                "enabled": True,
                "triggers": [
                    {
                        "type": "message",
                        "params": {"chat_id": -1001234567890},
                    }
                ],
                "filters": {"chat_id": -1001234567890},
                "handlers": [],
                "vars": {},
            }
        ]
    }
    rule = AutomationConfig.model_validate(payload).rules[0]
    assert isinstance(rule.triggers[0].params.chat_id, int)
    assert isinstance(rule.filters.chat_id, int)
    assert worker._match_chat(msg, rule.triggers[0].params.chat_id, None)
    assert worker._match_filter(rule.filters, msg)


def test_compute_next_run_interval_and_cron(tmp_path):
    worker = make_worker(tmp_path)
    now = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)

    trigger = TimerTriggerConfig(type="timer", params={"interval_seconds": 60})
    assert worker._compute_next_run(trigger, now) == now + timedelta(seconds=60)

    trigger = TimerTriggerConfig(type="timer", params={"cron": "*/5 * * * *"})
    next_dt = worker._compute_next_run(trigger, now)
    assert next_dt is not None
    assert next_dt > now


@pytest.mark.asyncio
async def test_timer_schedule_next_override(tmp_path):
    """验证 timer 触发后 schedule_next 能覆盖默认间隔计算。"""
    worker = make_worker(tmp_path)
    register_builtin_handlers()

    now = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    cfg = AutomationConfig(
        rules=[
            RuleConfig(
                id="r1",
                enabled=True,
                triggers=[
                    TimerTriggerConfig(
                        id="timer1",
                        type="timer",
                        params={"interval_seconds": 60},
                    )
                ],
                handlers=[
                    HandlerConfig(
                        handler="schedule_next",
                        params={"delay_seconds": 300},
                    )
                ],
            )
        ]
    )
    worker.config = cfg
    worker.state.set_trigger_next_run("r1", "timer1", now)

    import tg_signer.automation.engine as engine

    # 固定当前时间，避免定时循环受真实时间影响
    engine.get_now = lambda: now

    # 运行一次 timer_loop 周期后取消，模拟单轮触发
    task = asyncio.create_task(worker.timer_loop())
    await asyncio.sleep(0.01)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    next_run = worker.state.get_trigger_next_run("r1", "timer1")
    assert next_run == now + timedelta(seconds=300)


@pytest.mark.asyncio
async def test_timer_loop_survives_tick_exception(tmp_path):
    """单次 tick 抛异常不得让轮询退出。

    ``timer_loop`` 是 ``create_task`` 起的、无人 await:一旦抛出就只剩
    "Task exception was never retrieved",进程照常存活但所有 timer 规则
    永久不再触发 —— 典型的静默失效。
    """
    worker = make_worker(tmp_path)
    ticks: list[int] = []

    async def flaky_tick() -> None:
        ticks.append(len(ticks))
        if len(ticks) == 2:
            raise OSError("模拟 state.save() 失败")

    worker._tick_seconds = 0.01
    worker._tick_timers = flaky_tick

    task = asyncio.create_task(worker.timer_loop())
    try:
        deadline = asyncio.get_running_loop().time() + 5
        while len(ticks) < 5 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        assert not task.done(), "timer_loop 在异常后不应退出"
        assert len(ticks) >= 5, f"异常之后轮询应继续,实际 tick 次数={len(ticks)}"
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_on_edited_message_matches_message_trigger(tmp_path):
    """编辑消息应复用 message trigger 匹配链路。"""
    worker = make_worker(tmp_path)
    worker.config = AutomationConfig(
        rules=[
            RuleConfig(
                id="r1",
                enabled=True,
                triggers=[MessageTriggerConfig(type="message", params={"chat_id": 1})],
                handlers=[],
            )
        ]
    )
    events: list[tuple[str, str, int]] = []

    async def fake_run_rule(rule, event):
        events.append((rule.id, event.type, event.chat_id))

    worker._run_rule = fake_run_rule  # type: ignore[method-assign]
    msg = DummyMessage(text="edited", chat=DummyChat(id=1, username="room"))

    await worker.on_edited_message(None, msg)

    assert events == [("r1", "edited_message", 1)]


@pytest.mark.asyncio
async def test_on_edited_message_updates_cache(tmp_path):
    """编辑消息应覆盖缓存中的同 message_id 内容。"""
    worker = make_worker(tmp_path)
    worker.config = AutomationConfig(rules=[])

    original = DummyMessage(
        id=100, text="before", chat=DummyChat(id=1, username="room")
    )
    edited = DummyMessage(id=100, text="after", chat=DummyChat(id=1, username="room"))

    await worker.on_message(None, original)
    await worker.on_edited_message(None, edited)

    cached = worker.get_cached_messages(1)
    assert len(cached) == 1
    assert cached[0].text == "after"


def test_trigger_rejects_unknown_params_key():
    """强类型触发器应拒绝未定义字段，避免静默吞掉拼写错误。"""
    with pytest.raises(ValidationError):
        RuleConfig.model_validate(
            {
                "id": "invalid_trigger",
                "triggers": [
                    {
                        "type": "message",
                        "params": {"chat_id": 123, "interval_secondz": 1},
                    }
                ],
                "handlers": [{"handler": "send_text", "params": {"text": "ok"}}],
            }
        )


def test_trigger_rejects_legacy_flatten_fields():
    """只接受 type+params 结构，不再兼容平铺字段。"""
    with pytest.raises(ValidationError):
        RuleConfig.model_validate(
            {
                "id": "legacy_flatten",
                "triggers": [{"type": "message", "chat_id": 123, "reply_to_me": True}],
                "handlers": [{"handler": "send_text", "params": {"text": "ok"}}],
            }
        )


# ---------------------------------------------------------------------------
# 触发器类型清单：引擎与 config 必须一一对应
# ---------------------------------------------------------------------------


def test_engine_drives_every_declared_trigger_type():
    """引擎支持的触发器类型必须与 config 声明的完全一致。

    判别性：`TriggerConfig` 是 discriminated union，未知 type 在解析阶段就会被
    拒（不会静默忽略）。真正的隐患是清单漂移 —— 只改 config 会变成「配置合法、
    规则永不触发」，只改引擎则是死代码。任何一侧漏改，这条就会失败。
    """
    declared = set()
    for trigger_cls in get_args(get_args(TriggerConfig)[0]):
        declared |= set(get_args(trigger_cls.model_fields["type"].annotation))

    assert declared == set(SUPPORTED_TRIGGER_TYPES)


def test_iter_triggers_filter_by_type_keeps_the_original_index(tmp_path):
    """按类型取触发器时必须保留原下标，否则 trigger_id 会漂移。

    trigger_id 参与 state.json 里 next_run/last_run 的键，漂移会让已排期的
    timer 规则全部错位。
    """
    worker = make_worker(tmp_path)
    rule = RuleConfig(
        id="r1",
        triggers=[
            MessageTriggerConfig(type="message", params={"chat_id": 1}),
            TimerTriggerConfig(
                type="timer", params={"chat_id": 2, "interval_seconds": 60}
            ),
            MessageTriggerConfig(type="message", params={"chat_id": 3}),
        ],
        handlers=[HandlerConfig(handler="send_text", params={"text": "hi"})],
    )

    message_indexes = [i for i, _t in worker._iter_triggers(rule, MESSAGE_TRIGGER_TYPE)]
    assert message_indexes == [0, 2]

    timer_pairs = list(worker._iter_triggers(rule, TIMER_TRIGGER_TYPE))
    assert [i for i, _t in timer_pairs] == [1]
    assert timer_pairs[0][1].params.chat_id == 2

    assert list(worker._iter_triggers(rule, STARTUP_TRIGGER_TYPE)) == []


# ---------------------------------------------------------------------------
# B1: 后台任务必须在 client 启动之后创建
# ---------------------------------------------------------------------------


class FakeApp:
    """最小 client 替身：记录是否已经进入 ``async with``。"""

    def __init__(self):
        self.entered = False
        self.handlers: list[tuple] = []

    async def __aenter__(self):
        # 让出一次控制权：修复前 startup 任务在 __aenter__ 之前就已创建，
        # 会在这一步抢跑并看到 entered=False。
        await asyncio.sleep(0)
        self.entered = True
        return self

    async def __aexit__(self, *exc_info):
        return False

    def add_handler(self, *args, **kwargs):
        self.handlers.append((args, kwargs))


@pytest.mark.asyncio
async def test_background_tasks_start_after_client_is_started(tmp_path, monkeypatch):
    """startup/timer 任务必须在 ``async with self.app`` 内创建。

    修复前任务先于 client 启动被调度，冷启动首次 Telegram 调用直接抛
    "Client has not been started yet"，startup 被静默吞掉、timer 的
    next_run_at 还会照常推进（本次到期被消费）。
    """
    worker = make_worker(tmp_path)
    app = FakeApp()
    worker.app = app
    worker.user = object()  # 跳过登录
    worker.load_config = lambda cfg_cls=None: AutomationConfig(  # type: ignore[method-assign]
        rules=[
            RuleConfig(
                id="r1",
                enabled=True,
                triggers=[StartupTriggerConfig(type="startup", params={})],
                handlers=[],
            )
        ]
    )
    observed: list[bool] = []

    async def probe_run_rule(rule, event):
        observed.append(app.entered)

    worker._run_rule = probe_run_rule  # type: ignore[method-assign]

    async def fake_idle():
        # 等 startup 任务执行完再退出（真实 idle() 会永久阻塞）。
        for _ in range(200):
            if observed:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("startup 任务未执行")

    import tg_signer.automation.engine as engine

    monkeypatch.setattr(engine, "idle", fake_idle)

    await worker.run()

    assert observed == [True], "startup 任务在 client 启动前就被调度了"


@pytest.mark.asyncio
async def test_background_tasks_are_cancelled_on_exit(tmp_path, monkeypatch):
    """退出时仍要取消 startup/timer 任务（保留原 cancel-on-exit 语义）。"""
    worker = make_worker(tmp_path)
    worker._tick_seconds = 30
    app = FakeApp()
    worker.app = app
    worker.user = object()
    worker.load_config = lambda cfg_cls=None: AutomationConfig(rules=[])  # type: ignore[method-assign]

    running: list[bool] = []

    async def fake_idle():
        await asyncio.sleep(0)

    import tg_signer.automation.engine as engine

    monkeypatch.setattr(engine, "idle", fake_idle)
    real_timer_loop = worker.timer_loop

    async def tracked_timer_loop():
        running.append(True)
        try:
            await real_timer_loop()
        finally:
            running.append(False)

    worker.timer_loop = tracked_timer_loop  # type: ignore[method-assign]

    await worker.run()
    # 取消是异步投递的，让事件循环把 CancelledError 送进去。
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert running == [True, False]


# ---------------------------------------------------------------------------
# B2: 仅构造 worker 不应创建任务目录（state 懒加载）
# ---------------------------------------------------------------------------


def test_constructing_worker_does_not_create_task_dir(tmp_path):
    """构造 UserAutomation 不应触碰 <workdir>/automations/<task>。

    `automation list` 曾经因为构造默认任务名为 my_task 的 worker 而凭空建出
    `automations/my_task` 并把 my_task 列进输出。
    """
    workdir = tmp_path / "wd"
    worker = UserAutomation(
        workdir=workdir, session_dir=tmp_path / "sessions", account="acct"
    )

    assert worker._state is None
    assert not (workdir / "automations").exists()

    # 首次访问 state 时才真正落盘到任务目录。
    assert worker.state is not None
    assert (workdir / "automations" / "my_task" / "state.json").parent.is_dir()


def test_list_task_names_is_read_only(tmp_path):
    workdir = tmp_path / "wd"
    assert UserAutomation.list_task_names(workdir) == []
    assert not workdir.exists()

    (workdir / "automations" / "b_task").mkdir(parents=True)
    (workdir / "automations" / "a_task").mkdir(parents=True)
    (workdir / "automations" / "loose_file").write_text("x", encoding="utf-8")

    assert UserAutomation.list_task_names(workdir) == ["a_task", "b_task"]


# ---------------------------------------------------------------------------
# B4: export → import 往返不得按错误格式落盘
# ---------------------------------------------------------------------------


def _automation_payload() -> dict:
    return {
        "version": 1,
        "rules": [
            {
                "id": "r1",
                "enabled": True,
                "triggers": [{"type": "timer", "params": {"interval_seconds": 60}}],
                "handlers": [{"handler": "send_text", "params": {"text": "hi"}}],
            }
        ],
    }


def test_yaml_task_export_import_roundtrip_stays_loadable(tmp_path):
    """YAML 任务导出的是 YAML 原文，import 必须仍按 YAML 落回 config.yaml。"""
    yaml = pytest.importorskip("yaml")

    worker = make_worker(tmp_path)
    config_path = worker.task_dir / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(_automation_payload(), allow_unicode=True), encoding="utf-8"
    )

    exported = worker.export()
    assert "rules:" in exported  # 导出的确实是 YAML 原文

    worker.import_(exported)

    # 修复前：YAML 文本被写进 config.json，遮蔽 config.yaml 且解析失败。
    assert not (worker.task_dir / "config.json").exists()
    cfg = worker.load_config()
    assert [rule.id for rule in cfg.rules] == ["r1"]


def test_json_task_export_import_roundtrip_stays_loadable(tmp_path):
    worker = make_worker(tmp_path)
    config_path = worker.task_dir / "config.json"
    config_path.write_text(json.dumps(_automation_payload()), encoding="utf-8")

    worker.import_(worker.export())

    cfg = worker.load_config()
    assert [rule.id for rule in cfg.rules] == ["r1"]
    on_disk = json.loads(config_path.read_text(encoding="utf-8"))
    assert on_disk["rules"][0]["id"] == "r1"


def test_import_yaml_text_into_json_task_converts_format(tmp_path):
    """导入 YAML 文本到没有配置的任务时，目标文件是 JSON，内容必须是 JSON。"""
    yaml = pytest.importorskip("yaml")

    worker = make_worker(tmp_path)
    worker.import_(yaml.safe_dump(_automation_payload(), allow_unicode=True))

    target = worker.task_dir / "config.json"
    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8"))["rules"][0]["id"] == "r1"
    assert [rule.id for rule in worker.load_config().rules] == ["r1"]


def test_import_invalid_text_raises_clear_error(tmp_path):
    worker = make_worker(tmp_path)

    with pytest.raises(ValueError, match="导入"):
        worker.import_("这不是配置: [[[")


# ---------------------------------------------------------------------------
# B6: 用户名匹配大小写
# ---------------------------------------------------------------------------


def test_chat_username_matching_is_case_insensitive_by_default(tmp_path):
    """Telegram 用户名大小写不敏感：@MyChannel 必须命中配置里的 @mychannel。"""
    worker = make_worker(tmp_path)
    msg = DummyMessage(text="hi", chat=DummyChat(id=1, username="MyChannel"))

    assert worker._match_chat(msg, "@mychannel", None)

    trigger = MessageTriggerConfig(type="message", params={"chat_id": "@mychannel"})
    assert worker._match_message_trigger(trigger, msg)
    assert worker._match_filter(FilterConfig(chat_id="@mychannel"), msg)

    # ignore_case=False 时保持大小写敏感，避免把开关做成死字段。
    strict_trigger = MessageTriggerConfig(
        type="message", params={"chat_id": "@mychannel", "ignore_case": False}
    )
    assert not worker._match_message_trigger(strict_trigger, msg)
    assert not worker._match_filter(
        FilterConfig(chat_id="@mychannel", ignore_case=False), msg
    )


# ---------------------------------------------------------------------------
# B7: store_state(keys=[...]) 必须真正生效
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_state_keys_restrict_what_is_persisted(tmp_path):
    """`keys` 限定的子集必须生效：引擎不再无条件回写全部 ctx.vars。"""
    worker = make_worker(tmp_path)
    register_builtin_handlers()
    worker.config = AutomationConfig(
        rules=[
            RuleConfig(
                id="r1",
                enabled=True,
                triggers=[StartupTriggerConfig(type="startup", params={})],
                handlers=[
                    HandlerConfig(
                        handler="store_state", params={"keys": ["keep", "also"]}
                    )
                ],
                vars={"keep": 1, "also": 2, "drop": 3},
            )
        ]
    )

    event = Event(
        type="startup",
        chat_id=None,
        message=None,
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    await worker._run_rule(worker.config.rules[0], event)

    assert worker.state.get_rule_vars("r1") == {"keep": 1, "also": 2}


@pytest.mark.asyncio
async def test_run_rule_persists_all_vars_without_store_state(tmp_path):
    """未使用 store_state 时维持原契约：回写全部 ctx.vars。"""
    worker = make_worker(tmp_path)
    register_builtin_handlers()
    rule = RuleConfig(
        id="r1",
        enabled=True,
        triggers=[StartupTriggerConfig(type="startup", params={})],
        handlers=[],
        vars={"a": 1, "b": 2},
    )

    event = Event(
        type="startup",
        chat_id=None,
        message=None,
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    await worker._run_rule(rule, event)

    assert worker.state.get_rule_vars("r1") == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# B11: 消息缓存要限制 chat 数量
# ---------------------------------------------------------------------------


def test_message_cache_bounds_number_of_chats(tmp_path):
    worker = make_worker(tmp_path)
    worker._message_cache_chats_limit = 2

    for chat_id in (1, 2, 3):
        worker._cache_message(DummyMessage(id=1, text="x", chat=DummyChat(id=chat_id)))

    assert worker.get_cached_messages(1) == []
    assert len(worker.get_cached_messages(2)) == 1
    assert len(worker.get_cached_messages(3)) == 1
