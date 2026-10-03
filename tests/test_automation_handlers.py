import asyncio
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tg_signer.automation.handlers import (
    TemplateRenderError,
    ai_reply,
    blacklist_filter,
    delay,
    external_forward,
    extract_regex,
    load_plugins,
    random_pick,
    render_template,
    schedule_next,
    store_state,
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
async def test_extract_regex_default_var_is_referenceable(tmp_path):
    """未指定 ``var`` 时写入的名字必须能被模板引用。

    回归：旧实现退化成 ``var = str(group)``，也就是写进一个名为 ``"1"`` 的变量。
    而 ``{1}`` 在 ``str.format`` 里是**位置字段**而不是变量名，
    ``render_template`` 会直接抛 ``TemplateRenderError``（Replacement index 1 out
    of range）。于是 extract_regex 既没报错也没产出任何可用结果：规则链照常往下
    走，只是用户写下的捕获结果永远用不上，state.json 里还多出一个叫 ``"1"``
    的垃圾键。
    """
    from tg_signer.automation import handlers as handlers_mod

    ctx = _render_ctx(tmp_path)
    recorded = []
    ctx.log = lambda msg, level="INFO": recorded.append((level, msg))

    result = await extract_regex(
        _render_event("cooldown 42"), ctx, {"pattern": r"(\d+)"}
    )

    assert result == "continue"
    assert "1" not in ctx.vars, "仍写入了无法引用的数字变量名"
    var = handlers_mod._EXTRACT_REGEX_DEFAULT_VAR
    assert ctx.vars[var] == "42"
    # 这个名字必须真的能在模板里取到（这正是旧行为拿不到的部分）
    assert render_template(f"剩 {{{var}}} 分钟", _render_event(), ctx) == "剩 42 分钟"
    assert any(level == "WARNING" for level, _msg in recorded)


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


def test_load_plugins_skips_sync_handlers(tmp_path):
    """同步 handler 必须在加载期就被拒绝并留下警告。

    回归：只校验 ``callable``，同步函数会被注册进注册表，直到规则执行到它
    才在引擎里抛 ``object str can't be used in 'await' expression`` ——
    报错里既没有插件文件名也没有 handler 名。
    """
    handlers_dir = tmp_path / "handlers"
    handlers_dir.mkdir(parents=True, exist_ok=True)
    (handlers_dir / "plugin.py").write_text(
        "def sync_handler(event, ctx, params):\n"
        "    return 'continue'\n\n"
        "async def ok_handler(event, ctx, params):\n"
        "    return 'continue'\n\n"
        "HANDLERS = {'sync_one': sync_handler, 'ok_one': ok_handler}\n",
        encoding="utf-8",
    )

    load_plugins(handlers_dir, logging.getLogger("test"))

    from tg_signer.automation.handlers import get_handler

    assert get_handler("sync_one") is None
    assert get_handler("ok_one") is not None


def test_blacklist_filter_tolerates_non_string_keyword(tmp_path):
    """YAML 里不带引号的 ``- 123`` 会解析成 int，不得让 handler 中途 AttributeError。"""
    ctx = _render_ctx(tmp_path)

    result = asyncio.run(
        blacklist_filter(
            _render_event(text="hello 123 world"),
            ctx,
            {"keywords": [123, "hello"]},
        )
    )

    assert result == "stop", "合法关键词应照常命中"


def test_blacklist_filter_skips_bad_keyword_without_crashing(tmp_path):
    """只有非法关键词时不应崩溃，应跳过并继续。"""
    ctx = _render_ctx(tmp_path)

    result = asyncio.run(
        blacklist_filter(_render_event(text="hello"), ctx, {"keywords": [123]})
    )

    assert result == "continue"


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


def test_render_template_raises_on_unknown_placeholder(tmp_path):
    """引用不存在的变量必须抛异常，不能静默原样返回。

    回归：``render_template`` 原来 ``except Exception: return text``，而
    模板字典会把未知变量原样返回成 ``{nope}`` ——
    渲染「成功」了，输出却和输入一模一样。调用方拿到的就是这串字面量并直接
    发给 Telegram：群里看到 ``{nope}``，日志里一条告警都没有。
    """
    ctx = _render_ctx(tmp_path)
    with pytest.raises(TemplateRenderError, match="nope"):
        render_template("{nope}", _render_event(), ctx)


def test_render_template_allows_literal_braces_in_json_body(tmp_path):
    """正文里本来就带花括号（如 HTTP 回调的 JSON body）不是模板，必须原样放行。"""
    ctx = _render_ctx(tmp_path)
    body = '{"key": "value", "n": [1, 2]}'
    assert render_template(body, _render_event(), ctx) == body


def test_render_template_raises_when_message_is_absent(tmp_path):
    """``startup``/``timer`` 触发器没有 message，文档化的 {message.chat.title} 必然失败。

    回归：这两类事件 ``event.message is None``，``render_template`` 会塞一个
    ``SimpleNamespace(chat=None)``，于是 ``chat.title`` 抛 AttributeError 被吞掉，
    配置里照抄文档的模板就把字面量 ``{message.chat.title}`` 发进了群。
    """
    ctx = _render_ctx(tmp_path)
    event = _render_event()
    event.message = None
    with pytest.raises(TemplateRenderError):
        render_template("{message.chat.title}", event, ctx)


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

    渲染失败会抛 TemplateRenderError，关键是不能把 ``__globals__`` 的内容渲染出来。
    """
    ctx = _render_ctx(tmp_path)
    with pytest.raises(TemplateRenderError) as excinfo:
        render_template(template, _render_event(), ctx)
    assert "module" not in str(excinfo.value)


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


# ---------------------------------------------------------------------------
# 静默失效 / 失败开放 类修复
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blacklist_filter_missing_source_vars_fails_closed(tmp_path):
    """``source_var`` 指向不存在的变量时必须失败关闭，不能放行。

    回归：``resolve_blacklist_text`` 对缺失变量返回空串，而空串匹配不到任何
    关键词 —— 过滤器完全不起作用，后面的 ``send_text`` 照样把大模型输出发进群。
    文档里 ``ai_reply(store_var) → blacklist_filter(source_var) → send_text``
    这条链，只要 ``store_var`` 写错一个字母，广告/引流过滤就静默消失且无任何提示。
    """
    ctx = _render_ctx(tmp_path)
    ctx.vars["real"] = "干净的回复"
    event = _render_event()

    with pytest.raises(ValueError, match="missing_var"):
        await blacklist_filter(event, ctx, {"source_var": "missing_var"})

    with pytest.raises(ValueError):
        await blacklist_filter(
            event, ctx, {"source_vars": ["also_missing_a", "also_missing_b"]}
        )


@pytest.mark.asyncio
async def test_store_state_does_not_persist_none_for_absent_keys(tmp_path):
    """``store_state`` 不得把尚未产生的键写成 ``null``。

    回归：``ctx.vars.get(k)`` 没有默认值，未产生的键被存成 ``None``。下一轮
    ``load_state`` 把 ``None`` 灌回 ``ctx.vars`` 后该键就「存在」了，
    缺失键占位不再生效，模板把字符串 ``"None"`` 渲染出来
    并发送进群 —— 而字面量 ``{v}`` 永远看起来是正常的。
    这在「``extract_regex`` 先失败 / ``ai_reply`` 还没跑」的首轮是很常见的路径。
    """
    ctx = _render_ctx(tmp_path)
    ctx.vars["produced"] = "有值"

    await store_state(
        _render_event(),
        ctx,
        {"keys": ["produced", "not_produced_yet"]},
    )

    assert "not_produced_yet" not in ctx.vars, "未产生的键被凭空创建成 None"
    # 引擎正是按 ctx.persist_vars 回写，落盘的也只能是已产生的那个键
    assert ctx.persist_vars == {"produced": "有值"}

    # 真正落到 state.json 里的内容同样不能出现 null
    ctx.state.save()
    on_disk = json.loads(ctx.state.path.read_text(encoding="utf-8"))
    assert None not in on_disk["rules"]["r1"].values(), (
        "state.json 里被写进了 null，下次 load_state 会把它灌回 ctx.vars"
    )


@pytest.mark.asyncio
async def test_store_state_keeps_all_present_keys(tmp_path):
    """已产生的键必须照常持久化（防止修过头）。"""
    ctx = _render_ctx(tmp_path)
    ctx.vars["a"] = 1
    ctx.vars["b"] = 2
    ctx.vars["c"] = 3

    await store_state(_render_event(), ctx, {"keys": ["a", "b"]})

    assert ctx.persist_vars == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_random_pick_treats_string_choices_as_one_option(tmp_path):
    """``choices`` 写成字符串时必须整串作为一个选项。

    回归：``list("hello world")`` 把整串拆成单个字符，于是「随机发一条消息」
    变成随机发一个字母，而日志看起来完全正常、用户以为规则在工作。
    """
    ctx = _render_ctx(tmp_path)
    recorded = []
    ctx.log = lambda msg, level="INFO": recorded.append((level, msg))

    result = await random_pick(
        _render_event(), ctx, {"choices": "hello world", "var": "picked"}
    )

    assert result == "continue"
    assert ctx.vars["picked"] == "hello world", "字符串被拆成了单个字符"
    assert any(level == "WARNING" and "字符串" in msg for level, msg in recorded)


@pytest.mark.asyncio
async def test_random_pick_takes_dict_values(tmp_path):
    """``choices`` 是映射时取其值，并告警。"""
    ctx = _render_ctx(tmp_path)
    recorded = []
    ctx.log = lambda msg, level="INFO": recorded.append((level, msg))

    assert (
        await random_pick(
            _render_event(), ctx, {"choices": {"a": "甲", "b": "乙"}, "var": "picked"}
        )
        == "continue"
    )

    assert ctx.vars["picked"] in {"甲", "乙"}
    assert any(level == "WARNING" and "映射" in msg for level, msg in recorded)


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds", [float("inf"), float("-inf"), float("nan")])
async def test_delay_skips_non_finite_seconds(tmp_path, seconds):
    """``delay: .inf`` 必须跳过，不能睡到天荒地老。

    回归：``asyncio.sleep(inf)`` 永不返回，而该 task 一直持有该规则的
    ``asyncio.Lock``，于是这条规则之后的所有触发都排在它后面 —— 规则对进程
    生命周期而言等于死亡，日志里却没有任何错误。
    """
    ctx = _render_ctx(tmp_path)
    recorded = []
    ctx.log = lambda msg, level="INFO": recorded.append((level, msg))

    async def _no_sleep(_seconds):
        raise AssertionError("非有限值不应进入 sleep")

    monkey_sleep = asyncio.sleep
    asyncio.sleep = _no_sleep
    try:
        result = await delay(_render_event(), ctx, {"seconds": seconds})
    finally:
        asyncio.sleep = monkey_sleep

    assert result == "continue"
    assert any(level == "WARNING" for level, _msg in recorded)


@pytest.mark.asyncio
async def test_delay_clamps_oversized_seconds(tmp_path):
    """超过上限的等待必须按上限截断，避免一条规则挂起好几天。"""
    import tg_signer.automation.handlers as handlers_mod

    ctx = _render_ctx(tmp_path)
    recorded = []
    ctx.log = lambda msg, level="INFO": recorded.append((level, msg))
    slept = []

    async def _fake_sleep(seconds):
        slept.append(seconds)

    monkey_sleep = asyncio.sleep
    asyncio.sleep = _fake_sleep
    try:
        result = await delay(_render_event(), ctx, {"seconds": 10**9})
    finally:
        asyncio.sleep = monkey_sleep

    assert result == "continue"
    assert slept == [handlers_mod._MAX_DELAY_SECONDS]
    assert any(level == "WARNING" and "上限" in msg for level, msg in recorded)


def test_load_plugins_survives_plugin_that_calls_sys_exit(tmp_path):
    """插件在导入时 ``sys.exit()`` 不能带走整个进程的自动化任务。

    回归：``except Exception`` 抓不到 ``SystemExit``，异常直接穿过
    ``load_plugins``，而 ``UserAutomation.run`` 调用它时没有任何保护 ——
    一个残留顶层 ``main()`` 的插件文件就能让进程里所有任务一起消失。
    """
    from tg_signer.automation import handlers as handlers_mod

    handlers_dir = tmp_path / "handlers"
    handlers_dir.mkdir()
    (handlers_dir / "a_evil.py").write_text(
        "import sys\nsys.exit(1)\n", encoding="utf-8"
    )
    (handlers_dir / "b_good.py").write_text(
        "async def demo_plugin_handler(event, ctx, params):\n"
        "    return 'continue'\n"
        "\n"
        "HANDLERS = {'demo_plugin_handler': demo_plugin_handler}\n",
        encoding="utf-8",
    )

    logger = logging.getLogger("test_load_plugins_exit")
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    cap = _Capture()
    logger.addHandler(cap)
    logger.setLevel(logging.DEBUG)
    handlers_mod._REGISTRY.pop("demo_plugin_handler", None)
    try:
        load_plugins(handlers_dir, logger)
        registered = "demo_plugin_handler" in handlers_mod._REGISTRY
    finally:
        logger.removeHandler(cap)
        handlers_mod._REGISTRY.pop("demo_plugin_handler", None)

    assert registered, "坏插件把同目录的好插件也一起拖死了"
    assert any("a_evil" in msg and "退出" in msg for msg in records), (
        f"没有记录跳过了坏插件: {records}"
    )


def test_udp_protocol_error_received_logs_instead_of_printing(caplog):
    """UDP 错误必须进 tg-signer 日志文件，而不是 stdout。

    回归：``print`` 只到 stdout，在打包后的 CLI / ``multi-run`` 下通常没有可见
    控制台，「转发地址不可达」这类问题在日志文件里彻底无声。
    """
    import tg_signer.automation.handlers as handlers_mod

    with caplog.at_level(logging.WARNING, logger="tg-signer"):
        handlers_mod._UDPProtocol().error_received(OSError("boom"))

    assert "UDP error received" in caplog.text
