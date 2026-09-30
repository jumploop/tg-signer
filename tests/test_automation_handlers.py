import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tg_signer.automation.handlers import (
    ai_reply,
    blacklist_filter,
    external_forward,
    extract_regex,
    load_plugins,
    random_pick,
    render_template,
    schedule_next,
)
from tg_signer.automation.models import AutomationContext, Event, RuleStateStore


class DummyWorker:
    """仅用于验证 handler 调用与参数透传。"""

    def __init__(self):
        self.sent = []
        self.ai_tools = DummyAITools()

    async def send_message(
        self, chat_id, text, delete_after=None, reply_to_message_id=None
    ):
        self.sent.append((chat_id, text, delete_after, reply_to_message_id))

    def get_ai_tools(self):
        return self.ai_tools

    async def _call_telegram_api(self, operation, call, *, retry_on_floodwait=True):
        # 测试桩:直接调 call 并返回,不做限流/FloodWait
        return await call()


class DummyAITools:
    def __init__(self):
        self.calls = []

    async def get_reply(self, prompt, query):
        self.calls.append((prompt, query))
        return "AI-RESP"


class DummyClient:
    def __init__(self, history_messages):
        self.history_messages = history_messages

    async def get_chat_history(self, chat_id, limit):
        _ = chat_id
        for message in self.history_messages[:limit]:
            yield message


@pytest.mark.asyncio
async def test_extract_regex_sets_var(tmp_path):
    """extract_regex 应将捕获结果写入 ctx.vars。"""
    state = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    worker = DummyWorker()
    event = Event(
        type="message",
        chat_id=123,
        message=SimpleNamespace(text="cooldown 42"),
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    ctx = AutomationContext(
        vars={},
        state=state,
        client=None,
        logger=logging.getLogger("test"),
        worker=worker,
        workdir=tmp_path,
    )

    await extract_regex(event, ctx, {"pattern": r"cooldown (\d+)", "var": "x"})
    assert ctx.vars["x"] == "42"


@pytest.mark.asyncio
async def test_schedule_next_writes_state(tmp_path):
    """schedule_next 应写入 trigger 的 next_run_at。"""
    state = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    event = Event(
        type="timer",
        chat_id=None,
        message=None,
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    ctx = AutomationContext(
        vars={},
        state=state,
        client=None,
        logger=logging.getLogger("test"),
        worker=DummyWorker(),
        workdir=tmp_path,
    )

    await schedule_next(event, ctx, {"delay_seconds": 30})
    assert state.get_trigger_next_run("r1", "t1") == datetime(
        2024, 1, 1, 0, 0, 30, tzinfo=timezone.utc
    )


@pytest.mark.asyncio
async def test_schedule_next_from_var_minutes(tmp_path):
    """schedule_next 支持 from_var 按分钟解释。"""
    state = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    event = Event(
        type="timer",
        chat_id=None,
        message=None,
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    ctx = AutomationContext(
        vars={"cooldown": "5"},
        state=state,
        client=None,
        logger=logging.getLogger("test"),
        worker=DummyWorker(),
        workdir=tmp_path,
    )

    await schedule_next(
        event,
        ctx,
        {
            "from_var": "cooldown",
            "from_var_unit": "minutes",
            "offset_seconds": 30,
        },
    )
    assert state.get_trigger_next_run("r1", "t1") == datetime(
        2024, 1, 1, 0, 5, 30, tzinfo=timezone.utc
    )


@pytest.mark.asyncio
async def test_random_pick_sets_var(tmp_path):
    """random_pick 在指定 var 时不发送消息，仅写变量。"""
    state = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    event = Event(
        type="message",
        chat_id=1,
        message=SimpleNamespace(text="hi"),
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    ctx = AutomationContext(
        vars={},
        state=state,
        client=None,
        logger=logging.getLogger("test"),
        worker=DummyWorker(),
        workdir=tmp_path,
    )

    await random_pick(event, ctx, {"choices": ["a", "b"], "var": "pick"})
    assert ctx.vars["pick"] in {"a", "b"}


@pytest.mark.asyncio
async def test_blacklist_filter_source_var(tmp_path):
    """blacklist_filter 可过滤变量中的文本。"""
    state = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    event = Event(
        type="message",
        chat_id=1,
        message=SimpleNamespace(text="safe text"),
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    ctx = AutomationContext(
        vars={"ai_text": "This contains BAD word"},
        state=state,
        client=None,
        logger=logging.getLogger("test"),
        worker=DummyWorker(),
        workdir=tmp_path,
    )

    result = await blacklist_filter(
        event,
        ctx,
        {"source_var": "ai_text", "keywords": ["bad"], "ignore_case": True},
    )
    assert result == "stop"


@pytest.mark.asyncio
async def test_ai_reply_uses_recent_messages(tmp_path):
    """ai_reply 可按 recent_limit 读取历史消息作为输入。"""
    state = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    worker = DummyWorker()
    history = [
        SimpleNamespace(
            text="最新消息",
            caption=None,
            from_user=SimpleNamespace(
                username="neo", first_name=None, last_name=None, id=1
            ),
            sender_chat=None,
        ),
        SimpleNamespace(
            text="更早消息",
            caption=None,
            from_user=SimpleNamespace(
                username="trinity", first_name=None, last_name=None, id=2
            ),
            sender_chat=None,
        ),
    ]
    event = Event(
        type="message",
        chat_id=123,
        message=SimpleNamespace(text="当前消息", id=99),
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    ctx = AutomationContext(
        vars={},
        state=state,
        client=DummyClient(history),
        logger=logging.getLogger("test"),
        worker=worker,
        workdir=tmp_path,
    )

    result = await ai_reply(
        event,
        ctx,
        {
            "prompt": "你是测试助手",
            "recent_limit": 2,
            "store_var": "ai_text",
        },
    )
    assert result == "continue"
    assert ctx.vars["ai_text"] == "AI-RESP"
    _, query = worker.ai_tools.calls[0]
    assert "[@trinity] 更早消息" in query
    assert "[@neo] 最新消息" in query


def test_load_plugins_registers_handlers(tmp_path):
    """插件加载后应可通过 get_handler 获取到注册函数。"""
    handlers_dir = tmp_path / "handlers"
    handlers_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = handlers_dir / "plugin.py"
    plugin_path.write_text(
        "async def hello(event, ctx, params):\n"
        "    return 'continue'\n\n"
        "HANDLERS = {'plugin_hello': hello}\n",
        encoding="utf-8",
    )

    load_plugins(handlers_dir, logging.getLogger("test"))

    from tg_signer.automation.handlers import get_handler

    assert get_handler("plugin_hello") is not None


# ---------------------------------------------------------------------------
# P2 修复:模板取值收敛(禁止 dunder 属性链 / 下标)+ 配置正则的边界护栏
# ---------------------------------------------------------------------------


def _render_ctx(tmp_path):
    state = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    return AutomationContext(
        vars={},
        state=state,
        client=None,
        logger=logging.getLogger("test"),
        worker=DummyWorker(),
        workdir=tmp_path,
    )


def _render_event(text="hi"):
    return Event(
        type="message",
        chat_id=123,
        message=SimpleNamespace(text=text, id=7, chat=SimpleNamespace(id=123)),
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )


def test_render_template_substitutes_documented_placeholders(tmp_path):
    """文档化的占位符必须继续可用。"""
    ctx = _render_ctx(tmp_path)
    event = _render_event()
    assert render_template("说: {message.text}", event, ctx) == "说: hi"
    assert render_template("chat={chat_id}", event, ctx) == "chat=123"
    assert render_template("topic={message.chat.id}", event, ctx) == "topic=123"


def test_render_template_keeps_unknown_placeholders_verbatim(tmp_path):
    ctx = _render_ctx(tmp_path)
    assert render_template("{nope}", _render_event(), ctx) == "{nope}"


@pytest.mark.parametrize(
    "template",
    [
        "{message.__class__.__mro__}",
        "{message.__class__.__init__.__globals__}",
        "{message.__class__.__init__.__globals__[logging]}",
        "{event.message.__class__.__init__.__globals__}",
        "{message.__dict__}",
        "{message._private}",
        "{message.chat[id]}",
        "{message.chat.id.extra.deeper}",
    ],
)
def test_render_template_refuses_attribute_chain_escapes(tmp_path, template):
    """模板不能顺着属性链 / 下标读到模块全局变量之类的东西。

    渲染失败时返回原样文本(既有行为),关键是不能把 ``__globals__`` 的内容渲染出来。
    """
    ctx = _render_ctx(tmp_path)
    rendered = render_template(template, _render_event(), ctx)
    assert rendered == template
    assert "module" not in str(rendered)


@pytest.mark.asyncio
async def test_extract_regex_skips_oversized_pattern(tmp_path):
    ctx = _render_ctx(tmp_path)
    await extract_regex(_render_event(), ctx, {"pattern": "a" * 1000, "var": "x"})
    assert "x" not in ctx.vars


@pytest.mark.asyncio
async def test_extract_regex_skips_catastrophic_pattern(tmp_path):
    """嵌套无上限量词要被跳过,而不是真的去匹配到把事件循环卡死。"""
    ctx = _render_ctx(tmp_path)
    event = _render_event(text="a" * 2000 + "!")
    await asyncio.wait_for(
        extract_regex(event, ctx, {"pattern": r"(a+)+$", "var": "x"}), timeout=3
    )
    assert "x" not in ctx.vars


@pytest.mark.asyncio
async def test_blacklist_filter_skips_catastrophic_pattern(tmp_path):
    ctx = _render_ctx(tmp_path)
    event = _render_event(text="a" * 2000 + "!")
    result = await asyncio.wait_for(
        blacklist_filter(event, ctx, {"regex": r"(a+)+$"}), timeout=3
    )
    assert result == "continue"


@pytest.mark.asyncio
async def test_blacklist_filter_skips_invalid_regex(tmp_path):
    ctx = _render_ctx(tmp_path)
    result = await blacklist_filter(
        _render_event(), ctx, {"regex": "(unclosed", "keywords": []}
    )
    assert result == "continue"


# ---------------------------------------------------------------------------
# B8: external_forward 单个目标失败不得中断其余目标
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_external_forward_continues_after_target_failure(tmp_path, monkeypatch):
    """第一个目标抛异常时，第二个目标仍要收到转发。"""
    import tg_signer.automation.handlers as handlers

    sent: list[str] = []

    async def flaky_udp(cfg, message):
        _ = cfg, message
        raise OSError("udp boom")

    async def ok_http(cfg, message):
        sent.append(str(cfg.url))

    monkeypatch.setattr(handlers, "udp_forward", flaky_udp)
    monkeypatch.setattr(handlers, "http_api_callback", ok_http)

    ctx = _render_ctx(tmp_path)
    event = _render_event()
    result = await external_forward(
        event,
        ctx,
        {
            "targets": [
                {"type": "udp", "host": "127.0.0.1", "port": 9999},
                {"type": "http", "url": "http://127.0.0.1:1/hook"},
            ]
        },
    )

    assert result == "continue"
    assert sent == ["http://127.0.0.1:1/hook"]


# ---------------------------------------------------------------------------
# B9: blacklist_filter 的 keywords 裸字符串不得被逐字符拆分
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blacklist_filter_string_keyword_is_not_split(tmp_path):
    ctx = _render_ctx(tmp_path)

    # "abcd" 必须整体作为一个关键词：文本 "abc" 不含 "abcd" → 不拦截。
    result = await blacklist_filter(
        _render_event(text="abc"), ctx, {"keywords": "abcd"}
    )
    assert result == "continue"

    # 列表形式照旧生效。
    result = await blacklist_filter(
        _render_event(text="abcd"), ctx, {"keywords": ["abcd"]}
    )
    assert result == "stop"


# ---------------------------------------------------------------------------
# B10: include_current 不得把当前消息重复拼进 prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_include_current_does_not_duplicate_current_message(tmp_path):
    """当前消息已在历史里时，prompt 只能出现一次。"""
    state = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    worker = DummyWorker()
    current = SimpleNamespace(
        text="当前消息",
        caption=None,
        from_user=SimpleNamespace(
            username="neo", first_name=None, last_name=None, id=1
        ),
        sender_chat=None,
    )
    older = SimpleNamespace(
        text="更早消息",
        caption=None,
        from_user=SimpleNamespace(
            username="trinity", first_name=None, last_name=None, id=2
        ),
        sender_chat=None,
    )
    event = Event(
        type="message",
        chat_id=123,
        message=SimpleNamespace(text="当前消息", id=99),
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    ctx = AutomationContext(
        vars={},
        state=state,
        client=DummyClient([current, older]),
        logger=logging.getLogger("test"),
        worker=worker,
        workdir=tmp_path,
    )

    result = await ai_reply(
        event,
        ctx,
        {"prompt": "p", "recent_limit": 2, "include_current": True, "store_var": "o"},
    )

    assert result == "continue"
    _, query = worker.ai_tools.calls[0]
    assert query.count("当前消息") == 1
    assert "[current]" not in query


@pytest.mark.asyncio
async def test_include_current_marks_message_missing_from_history(tmp_path):
    """当前消息不在历史里时保留 [current] 标记。"""
    state = RuleStateStore(tmp_path / "state.json", logging.getLogger("test"))
    worker = DummyWorker()
    older = SimpleNamespace(
        text="更早消息",
        caption=None,
        from_user=SimpleNamespace(
            username="trinity", first_name=None, last_name=None, id=2
        ),
        sender_chat=None,
    )
    event = Event(
        type="message",
        chat_id=123,
        message=SimpleNamespace(text="当前消息", id=99),
        now=datetime(2024, 1, 1, tzinfo=timezone.utc),
        trigger_id="t1",
        rule_id="r1",
    )
    ctx = AutomationContext(
        vars={},
        state=state,
        client=DummyClient([older]),
        logger=logging.getLogger("test"),
        worker=worker,
        workdir=tmp_path,
    )

    result = await ai_reply(
        event,
        ctx,
        {"prompt": "p", "recent_limit": 1, "include_current": True, "store_var": "o"},
    )

    assert result == "continue"
    _, query = worker.ai_tools.calls[0]
    assert query.count("当前消息") == 1
    assert "[current] 当前消息" in query
