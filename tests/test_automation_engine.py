import asyncio
import contextlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tg_signer.automation.engine import UserAutomation
from tg_signer.automation.handlers import register_builtin_handlers
from tg_signer.automation.models import RuleStateStore
from tg_signer.config import (
    AutomationConfig,
    FilterConfig,
    HandlerConfig,
    MessageTriggerConfig,
    RuleConfig,
    TimerTriggerConfig,
)


class AutomationHarness(UserAutomation):
    """测试专用实例，避免触发真实 client 初始化与网络依赖。"""

    def __init__(self, tmp_path):
        import logging
        from collections import OrderedDict, defaultdict

        self.task_name = "t"
        self._account = "test_account"
        self._workdir = tmp_path
        self._tasks_dir = "automations"
        self.logger = logging.getLogger("tg-signer")
        _ = self.task_dir  # 触发目录创建
        self.state = RuleStateStore(self.task_dir / "state.json", self.logger)
        self._tick_seconds = 1.0
        self._message_cache = defaultdict(OrderedDict)
        self._message_cache_limit = 200
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
