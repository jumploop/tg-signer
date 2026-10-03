import asyncio
import importlib.util
import logging
import os
import random
import re
import string
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, Iterable, Literal, Optional

import httpx
from pyrogram.types import Message

from tg_signer.config import HttpCallback, UDPForward
from tg_signer.notification.server_chan import sc_send
from tg_signer.utils import message_text, safe_regex_search

from .models import AutomationContext, Event

logger = logging.getLogger("tg-signer")

# 统一 handler 返回值语义：
# - continue: 继续执行后续 handler
# - stop/defer: 中断当前规则链
HandlerResult = Literal["continue", "stop", "defer"]
HandlerFn = Callable[
    [Event, AutomationContext, Dict[str, Any]], Awaitable[HandlerResult]
]

_REGISTRY: Dict[str, HandlerFn] = {}


class _UDPProtocol(asyncio.DatagramProtocol):
    """内部使用的UDP协议处理类"""

    def error_received(self, exc):
        # 用 logger 而不是 print：UDP 套接字错误走 print 只到 stdout，
        # 在打包后的 CLI / multi-run 下通常根本没有可见的控制台，
        # 于是「转发地址不可达」这类问题在 tg-signer 日志文件里完全看不到。
        logger.warning("UDP error received: %s", exc)


async def udp_forward(f: UDPForward, message: Message):
    data = str(message).encode("utf-8")
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        _UDPProtocol, remote_addr=(f.host, f.port)
    )
    try:
        transport.sendto(data)
    finally:
        transport.close()


async def http_api_callback(f: HttpCallback, message: Message):
    headers = f.headers or {}
    headers.update({"Content-Type": "application/json"})
    content = str(message).encode("utf-8")
    async with httpx.AsyncClient() as client:
        await client.post(
            str(f.url),
            content=content,
            headers=headers,
            timeout=10,
        )


# 模板里允许的最大属性层级:``{message.text}`` 是文档化用法,
# ``{message.chat.title}`` 也保留,再深就没有正当理由了。
_MAX_TEMPLATE_ATTR_DEPTH = 2

# `delay` handler 允许的最长等待。超过这个值几乎必然是配置写错（如多打了几
# 个零），而它的后果是那条规则被永久占住，所以按上限截断并告警。
_MAX_DELAY_SECONDS = 24 * 60 * 60


class _SafeTemplateFormatter(string.Formatter):
    """只允许 ``{name}`` 与 ``{name.attr[.attr]}`` 的基础模板语法。

    ``str.format_map`` 默认允许任意属性链与下标取值,而 ``mapping`` 里放的是
    真实的 Message / Event 对象,于是配置里写 ``{message.__class__.__mro__}``
    或 ``{event.message.__class__.__init__.__globals__[httpx]}`` 就能读到本模块的
    全局变量。这里收紧到:不允许下标、属性层级 <= 2、任何一段都不以下划线开头
    —— 既保留文档化的 ``{message.text}``,又堵掉全部 dunder 逃逸路径。
    """

    def get_field(self, field_name, args, kwargs):
        if "[" in field_name or "]" in field_name:
            raise ValueError(f"模板不支持下标取值: {field_name!r}")
        parts = field_name.split(".")
        if len(parts) > _MAX_TEMPLATE_ATTR_DEPTH + 1:
            raise ValueError(f"模板属性层级过深: {field_name!r}")
        if any(not part or part.startswith("_") for part in parts):
            raise ValueError(f"模板字段非法: {field_name!r}")
        value, used = super().get_field(parts[0], args, kwargs)
        for attr in parts[1:]:
            value = getattr(value, attr)
        return value, used


_TEMPLATE_FORMATTER = _SafeTemplateFormatter()

# 判断一段文本「是不是模板」：``{`` 后面紧跟标识符字符（字母/下划线）才算。
# 用来把「模板没渲染出来」和「正文里本来就有花括号」区分开：HTTP 回调 /
# server_chan 的 body 常常直接写 JSON（``{"key": "value"}``），``{`` 后面是
# 引号，不是模板，必须原样发送。
# 这里故意收得比合法字段更宽：``{message.__class__[x]}`` 这类被沙箱拒绝的
# 形状也要判为「模板」，否则它会被当成普通文本原样发进群里。
_TEMPLATE_REFERENCE_RE = re.compile(r"\{[A-Za-z_][^{}]*\}")


class TemplateRenderError(ValueError):
    """模板渲染失败（引用了不存在的变量或属性）。"""


class _TrackingFormatDict(dict):
    """记录所有未命中的变量名，并保留 ``{name}`` 占位文本。

    未知变量原样返回成 ``"{name}"``，于是渲染「成功」了、输出却和输入一模一样
    —— 调用方完全无法察觉变量名写错了。
    """

    def __init__(self):
        super().__init__()
        self.missing: list[str] = []

    def __missing__(self, key):
        self.missing.append(key)
        return "{" + key + "}"


def render_template(text: Any, event: Event, ctx: AutomationContext) -> Any:
    """渲染 ``text`` 中的模板变量。

    渲染失败必须**抛异常**：原来 ``except Exception: return text`` 会在无任何
    日志的情况下把未渲染的模板原样交给调用方，而调用方直接把它发给 Telegram。
    最典型的是文档化的 ``{message.chat.title}`` 用在 ``startup``/``timer`` 触发器
    上（这两类事件 ``message is None``，``chat`` 也就是 ``None``），于是群里
    收到一条字面量 ``{message.chat.title}``，日志里一条告警都没有。

    正文里本来就带花括号（JSON 请求体）不算模板，仍按原样返回。
    """
    if not isinstance(text, str):
        return text
    message = event.message or SimpleNamespace(text="", id=None, chat=None)
    mapping = _TrackingFormatDict()
    mapping.update(ctx.vars)
    mapping.update(
        {
            "chat_id": event.chat_id,
            "now": event.now,
            "message": message,
            "event": event,
        }
    )
    try:
        rendered = _TEMPLATE_FORMATTER.vformat(text, (), mapping)
    except Exception as exc:  # noqa: BLE001
        if not _TEMPLATE_REFERENCE_RE.search(text):
            # 没有模板引用，只是普通的花括号文本（如 JSON body），原样使用。
            return text
        raise TemplateRenderError(f"模板渲染失败: {text!r} ({exc})") from exc
    if mapping.missing:
        raise TemplateRenderError(
            f"模板引用了不存在的变量 {sorted(set(mapping.missing))}: {text!r}"
        )
    return rendered


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def message_sender(message: Message) -> str:
    if message is None:
        return "unknown"
    from_user = message.from_user
    if from_user is not None:
        username = from_user.username
        if username:
            return f"@{username}"
        first_name = from_user.first_name or ""
        last_name = from_user.last_name or ""
        full_name = f"{first_name} {last_name}".strip()
        if full_name:
            return full_name
        user_id = from_user.id
        return str(user_id)
    sender_chat = message.sender_chat
    if sender_chat is not None:
        title = sender_chat.title or sender_chat.username
        if title:
            return str(title)
    return "unknown"


async def resolve_ai_input(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> str:
    # 显式 input 优先；若未提供，再根据 recent_limit 动态拼装上下文。
    input_text = params.get("input")
    if input_text is not None:
        return str(render_template(input_text, event, ctx))

    recent_limit = params.get("recent_limit", params.get("recent_messages"))
    if recent_limit is None:
        return message_text(event.message)
    try:
        recent_limit = int(recent_limit)
    except (TypeError, ValueError):
        recent_limit = 0
    if recent_limit <= 0:
        return message_text(event.message)

    history_chat_id = (
        params.get("history_chat_id") or params.get("chat_id") or event.chat_id
    )
    if history_chat_id is None:
        ctx.log(
            "ai_reply: 缺少history_chat_id/chat_id，无法读取历史消息", level="WARNING"
        )
        return message_text(event.message)

    lines: list[str] = []
    texts: list[str] = []

    async def _fetch_history():
        msgs = []
        # get_chat_history 通常返回新->旧,这里先按新->旧收集,reverse 后成旧->新
        async for msg in ctx.client.get_chat_history(
            history_chat_id, limit=recent_limit
        ):
            msgs.append(msg)
        return msgs

    try:
        # 走 worker 的统一限流 + FloodWait 重试
        messages = await ctx.worker._call_telegram_api(
            "ai_reply.get_chat_history", _fetch_history
        )
    except Exception as exc:  # noqa: BLE001
        ctx.log(f"ai_reply: 读取历史消息失败 ({exc})", level="WARNING")
        return message_text(event.message)

    for msg in messages:
        text = message_text(msg).strip()
        if not text:
            continue
        texts.append(text)
        lines.append(f"[{message_sender(msg)}] {text}")

    lines.reverse()
    texts.reverse()
    if as_bool(params.get("include_current", False)):
        current_text = message_text(event.message).strip()
        # 当前消息通常就是历史里最新的一条:此时 lines[-1] 是 "[sender] 文本",
        # 与 "[current] 文本" 永不相等(旧实现因此失效,当前消息被重复拼进 prompt)。
        # 这里比对纯文本,已存在就不再追加。
        if current_text and (not texts or texts[-1] != current_text):
            lines.append(f"[current] {current_text}")
    if not lines:
        return message_text(event.message)

    separator = params.get("history_separator")
    if separator is None:
        separator = "\n"
    return str(separator).join(lines)


def resolve_blacklist_text(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> str:
    # 按优先级取过滤文本：text > source_var/source_vars > 当前消息。
    source_text = params.get("text")
    if source_text is not None:
        return str(render_template(source_text, event, ctx))

    source_var = params.get("source_var")
    if source_var:
        if source_var not in ctx.vars:
            # 变量不存在时必须**失败关闭**（抛异常 → 引擎记 ERROR 并中断该
            # 规则），而不是拿空串去过滤。空串什么都匹配不到，于是过滤器
            # 静默失效、后面的 send_text 照样把大模型输出发进群里。
            # 这在文档化的 ai_reply(store_var) → blacklist_filter(source_var)
            # → send_text 链里是最常见的失败：store_var 写错一个字母，
            # 「广告/引流/返利」过滤就完全不起作用，且没有任何提示。
            raise ValueError(
                f"blacklist_filter: 变量 {source_var!r} 不存在，无法判断内容，"
                f"已中止该规则（可用变量: {sorted(ctx.vars)}）"
            )
        return str(ctx.vars.get(source_var) or "")

    source_vars = params.get("source_vars")
    if isinstance(source_vars, list):
        present = [name for name in source_vars if ctx.vars.get(name)]
        if source_vars and not present:
            raise ValueError(
                f"blacklist_filter: source_vars={source_vars} 全都不存在，"
                f"无法判断内容，已中止该规则（可用变量: {sorted(ctx.vars)}）"
            )
        values = [str(ctx.vars.get(name)) for name in present]
        return "\n".join(values)

    return message_text(event.message)


def register(name: str, fn: HandlerFn) -> None:
    _REGISTRY[name] = fn


def get_handler(name: str) -> Optional[HandlerFn]:
    return _REGISTRY.get(name)


def list_handlers() -> Iterable[str]:
    return sorted(_REGISTRY.keys())


def load_plugins(handlers_dir: Path, logger: logging.Logger) -> None:
    if not handlers_dir.is_dir():
        logger.debug("插件目录不存在，跳过加载: %s", handlers_dir)
        return
    loaded_modules = 0
    registered_handlers = 0
    for path in sorted(handlers_dir.glob("*.py")):
        module_name = f"tg_signer_user_handlers_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                logger.warning(f"无法加载插件: {path}")
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded_modules += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"插件加载失败: {path} ({exc})")
            continue
        except (SystemExit, KeyboardInterrupt) as exc:
            # `except Exception` 抓不到 SystemExit / KeyboardInterrupt：插件在
            # 模块顶层调用 sys.exit()（或 import 到会调 sys.exit 的库）时，
            # 异常会直接穿过 load_plugins —— 而它由 UserAutomation.run 调用且
            # 没有任何保护，结果是一个坏插件文件把**整个进程**里所有自动化
            # 任务一起带走。这里按「加载失败」处理，只跳过这个文件。
            logger.warning(f"插件在导入时退出，已跳过: {path} ({exc!r})")
            continue
        handlers = getattr(module, "HANDLERS", None)
        if not isinstance(handlers, dict):
            logger.warning(f"插件未提供HANDLERS: {path}")
            continue
        for name, fn in handlers.items():
            if name in _REGISTRY:
                logger.warning(f"插件handler与内置冲突，跳过: {name}")
                continue
            if not callable(fn):
                logger.warning(f"插件handler不可调用，跳过: {name}")
                continue
            # 只接受 async handler：引擎一律 `await handler(...)`，同步函数
            # 会在此处直接 TypeError「object str can't be used in 'await'
            # expression」，而且是在规则执行到这一步时才炸 —— 错误信息里完全
            # 看不到是哪个 handler、哪个文件。
            if not asyncio.iscoroutinefunction(fn):
                logger.warning(f"插件handler不是async，跳过: {name} ({path.name})")
                continue
            _REGISTRY[name] = fn
            registered_handlers += 1
            logger.debug("插件 handler 注册成功: %s (%s)", name, path.name)
    logger.info(
        "插件加载完成: dir=%s, modules=%s, handlers=%s",
        handlers_dir,
        loaded_modules,
        registered_handlers,
    )


async def send_text(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    text = params.get("text") or ""
    if not text:
        ctx.log("send_text: 空文本", level="WARNING")
        return "stop"
    chat_id = params.get("chat_id") or event.chat_id
    if chat_id is None:
        ctx.log("send_text: 缺少chat_id", level="WARNING")
        return "stop"
    text = render_template(text, event, ctx)
    delete_after = params.get("delete_after")
    reply_to_message_id = params.get("reply_to_message_id")
    ctx.log(
        f"send_text: chat_id={chat_id}, delete_after={delete_after}, reply_to={reply_to_message_id}",
        level="DEBUG",
    )
    await ctx.worker.send_message(
        chat_id,
        text,
        delete_after=delete_after,
        reply_to_message_id=reply_to_message_id,
    )
    return "continue"


async def reply_text(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    text = params.get("text") or ""
    if not text:
        ctx.log("reply_text: 空文本", level="WARNING")
        return "stop"
    chat_id = params.get("chat_id") or event.chat_id
    if chat_id is None:
        ctx.log("reply_text: 缺少chat_id", level="WARNING")
        return "stop"
    reply_to_message_id = params.get("reply_to_message_id")
    if reply_to_message_id is None and event.message:
        reply_to_message_id = event.message.id
    if reply_to_message_id is None:
        ctx.log("reply_text: 缺少reply_to_message_id", level="WARNING")
        return "stop"
    text = render_template(text, event, ctx)
    delete_after = params.get("delete_after")
    ctx.log(
        f"reply_text: chat_id={chat_id}, reply_to={reply_to_message_id}, delete_after={delete_after}",
        level="DEBUG",
    )
    await ctx.worker.send_message(
        chat_id,
        text,
        delete_after=delete_after,
        reply_to_message_id=reply_to_message_id,
    )
    return "continue"


# extract_regex 未显式指定 var 时使用的默认变量名。必须是一个能写成 {name}
# 引用的标识符 —— 数字开头的名字在 str.format 里是位置字段，永远引用不到。
_EXTRACT_REGEX_DEFAULT_VAR = "extracted"


async def extract_regex(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    pattern = params.get("pattern") or params.get("regex")
    if not pattern:
        ctx.log("extract_regex: 缺少pattern", level="WARNING")
        return "stop"
    text = params.get("text")
    if text is None:
        text = message_text(event.message)
    flags = re.IGNORECASE if params.get("ignore_case", True) else 0
    try:
        match = safe_regex_search(pattern, text, flags=flags)
    except ValueError as exc:
        ctx.log(f"extract_regex: {exc}", level="WARNING")
        return "continue"
    if not match:
        ctx.log("extract_regex: 未匹配到结果", level="DEBUG")
        return "continue"
    group = params.get("group", 1)
    var = params.get("var")
    try:
        value = match.group(group)
    except Exception:  # noqa: BLE001
        value = match.group(0)
    if not var:
        # 原来这里退化成 var = str(group)，也就是把结果写进名为 "1" 的变量 ——
        # 而 "{1}" 在 str.format 里是**位置字段**（不是变量名），没有任何方式能
        # 引用到它。extract_regex 于是既没报错也没产出可用结果：规则链照常往下
        # 走，只是用户写下的捕获结果永远用不上。这个默认值是纯损失。
        # 现改为一个能被模板引用的名字，并告警让用户知道自己该显式写 var。
        var = _EXTRACT_REGEX_DEFAULT_VAR
        ctx.log(
            f"extract_regex: 未指定 var，结果写入默认变量 {var!r}"
            "（如需其它名字请显式设置 var）",
            level="WARNING",
        )
    ctx.vars[var] = value
    ctx.log(f"extract_regex: 写入变量 {var}={value}", level="DEBUG")
    return "continue"


async def ai_reply(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    prompt = params.get("prompt")
    if not prompt:
        ctx.log("ai_reply: 缺少prompt", level="WARNING")
        return "stop"
    prompt = str(render_template(prompt, event, ctx))
    text = await resolve_ai_input(event, ctx, params)
    reply_to_message_id = params.get("reply_to_message_id")
    if reply_to_message_id is None and event.message:
        reply_to_message_id = event.message.id
    ctx.log(
        f"ai_reply: 调用模型, prompt_len={len(prompt)}, input_len={len(text)}",
        level="DEBUG",
    )
    result = await ctx.worker.get_ai_tools().get_reply(prompt, text)
    store_var = params.get("store_var") or params.get("output_var")
    if store_var:
        # store_var/output_var 语义：只写变量，不直接发送。
        ctx.vars[store_var] = result
        ctx.log(f"ai_reply: 已写入变量 {store_var}", level="DEBUG")
        return "continue"
    chat_id = params.get("chat_id") or event.chat_id
    if chat_id is None:
        ctx.log("ai_reply: 缺少chat_id", level="WARNING")
        return "stop"
    delete_after = params.get("delete_after")
    ctx.log(
        f"ai_reply: 发送回复 chat_id={chat_id}, reply_to={reply_to_message_id}",
        level="DEBUG",
    )
    await ctx.worker.send_message(
        chat_id,
        result,
        delete_after=delete_after,
        reply_to_message_id=reply_to_message_id,
    )
    return "continue"


async def blacklist_filter(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    text = resolve_blacklist_text(event, ctx, params)
    ignore_case = as_bool(params.get("ignore_case", False))
    matched_text = text.lower() if ignore_case else text
    keywords = params.get("keywords") or []
    if isinstance(keywords, str):
        # 裸字符串必须整体当成一个关键词:否则 "abcd" 会退化成 4 个单字符关键词,
        # 含 "a" 的正常文本会被误杀。
        keywords = [keywords]
    elif not isinstance(keywords, (list, tuple, set)):
        ctx.log(
            f"blacklist_filter: keywords 类型非法 ({type(keywords).__name__})，已忽略",
            level="WARNING",
        )
        keywords = []
    for kw in keywords:
        if not isinstance(kw, str):
            # YAML 不带引号的 - 123 会解析成 int，kw.lower() 直接 AttributeError，
            # 而它发生在规则执行途中（前面几条 handler 已经跑过了）。
            ctx.log(
                f"blacklist_filter: 跳过非字符串关键词 {kw!r} ({type(kw).__name__})",
                level="WARNING",
            )
            continue
        if not kw:
            continue
        needle = kw.lower() if ignore_case else kw
        if needle in matched_text:
            ctx.log(f"blacklist_filter: 关键词命中 {kw}", level="DEBUG")
            return "stop"
    regex = params.get("regex")
    if regex:
        try:
            flags = re.IGNORECASE if ignore_case else 0
            if safe_regex_search(regex, text, flags=flags):
                ctx.log("blacklist_filter: regex 命中", level="DEBUG")
                return "stop"
        except ValueError as exc:
            ctx.log(f"blacklist_filter: {exc}", level="WARNING")
    return "continue"


async def delay(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    _ = event
    seconds = params.get("seconds")
    if seconds is None:
        seconds = params.get("delay_seconds", 0)
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        seconds = 0
    # nan / inf / 超大值与「等一会儿」都不是一回事：
    # sleep(inf) 永不返回，sleep(nan) 立刻返回；而 handler 是被 engine 的
    # 独立 task 执行的，任务会一直持有该规则的 asyncio.Lock（engine 里
    # async with self._rule_lock(rule.id)），于是**这条规则之后的所有触发都
    # 排在这个永不结束的任务后面**，规则等于永久死亡，日志里还没有任何错误。
    if seconds != seconds or seconds in (float("inf"), float("-inf")):
        ctx.log(
            f"delay: seconds 不是有限数值，已跳过等待: {params.get('seconds')!r}",
            level="WARNING",
        )
        return "continue"
    if seconds > _MAX_DELAY_SECONDS:
        ctx.log(
            f"delay: seconds={seconds} 超过上限 {_MAX_DELAY_SECONDS}s，已按上限截断",
            level="WARNING",
        )
        seconds = _MAX_DELAY_SECONDS
    if seconds > 0:
        ctx.log(f"delay: sleep {seconds}s", level="DEBUG")
        await asyncio.sleep(seconds)
    return "continue"


async def forward(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    if not event.message:
        ctx.log("forward: 缺少message", level="WARNING")
        return "stop"
    to_chat_id = params.get("chat_id") or params.get("to_chat_id")
    if to_chat_id is None:
        ctx.log("forward: 缺少chat_id", level="WARNING")
        return "stop"
    from_chat_id = params.get("from_chat_id") or event.chat_id
    message_id = params.get("message_id") or event.message.id
    ctx.log(
        f"forward: from={from_chat_id}, to={to_chat_id}, message_id={message_id}",
        level="DEBUG",
    )
    await ctx.worker._call_telegram_api(
        "forward",
        lambda: ctx.client.forward_messages(
            to_chat_id,
            from_chat_id,
            message_id,
        ),
    )
    return "continue"


async def external_forward(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    if not event.message:
        ctx.log("external_forward: 缺少message", level="WARNING")
        return "stop"
    targets = params.get("targets") or []
    success_count = 0
    failure_count = 0
    for target in targets:
        if not isinstance(target, dict):
            continue
        t_type = target.get("type")
        if t_type == "udp":
            try:
                cfg = UDPForward.model_validate(target)
            except Exception:  # noqa: BLE001
                ctx.log("external_forward: UDP配置无效", level="WARNING")
                failure_count += 1
                continue
            try:
                await udp_forward(cfg, event.message)
            except Exception as exc:  # noqa: BLE001
                # 单个目标失败不得中断后续目标,也不应打断整条 handler 链。
                failure_count += 1
                ctx.log(f"external_forward: UDP转发失败 ({exc})", level="WARNING")
                continue
            success_count += 1
        elif t_type == "http":
            try:
                cfg = HttpCallback.model_validate(target)
            except Exception:  # noqa: BLE001
                ctx.log("external_forward: HTTP配置无效", level="WARNING")
                failure_count += 1
                continue
            try:
                await http_api_callback(cfg, event.message)
            except Exception as exc:  # noqa: BLE001
                failure_count += 1
                ctx.log(f"external_forward: HTTP回调失败 ({exc})", level="WARNING")
                continue
            success_count += 1
        else:
            ctx.log(f"external_forward: 未知目标类型 {t_type}", level="DEBUG")
    ctx.log(
        f"external_forward: 转发完成 success={success_count}, failed={failure_count}",
        level="DEBUG",
    )
    return "continue"


async def server_chan(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    send_key = params.get("send_key") or os.environ.get("SERVER_CHAN_SEND_KEY")
    if not send_key:
        ctx.log("server_chan: 未配置SendKey", level="WARNING")
        return "stop"
    title = params.get("title") or "Automation"
    body = params.get("body")
    if body is None:
        body = message_text(event.message)
    title = render_template(title, event, ctx)
    body = render_template(body, event, ctx)
    ctx.log(
        f"server_chan: 发送通知 title={str(title)[:32]}",
        level="DEBUG",
    )
    await sc_send(send_key, title, body)
    return "continue"


async def schedule_next(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    # 支持 trigger_id / target_trigger_id 两种命名，默认回落为当前触发器。
    target_trigger_id = (
        params.get("trigger_id") or params.get("target_trigger_id") or event.trigger_id
    )
    # 先解析基础 delay，再叠加 offset，最终写入 next_run_at。
    delay_seconds = params.get("delay_seconds")
    if delay_seconds is None:
        delay_minutes = params.get("delay_minutes")
        try:
            delay_seconds = float(delay_minutes or 0) * 60
        except (TypeError, ValueError):
            delay_seconds = 0
    from_var = params.get("from_var")
    if from_var:
        try:
            value = float(ctx.vars.get(from_var, delay_seconds))
            unit = str(params.get("from_var_unit") or "").lower().strip()
            if not unit and as_bool(params.get("from_var_minutes", False)):
                unit = "minutes"
            if unit in {"minute", "minutes", "min", "m"}:
                delay_seconds = value * 60
            else:
                delay_seconds = value
        except (TypeError, ValueError):
            pass
    offset_seconds = params.get("offset_seconds")
    if offset_seconds is None:
        offset_minutes = params.get("offset_minutes")
        try:
            offset_seconds = float(offset_minutes or 0) * 60
        except (TypeError, ValueError):
            offset_seconds = 0
    try:
        total_seconds = float(delay_seconds) + float(offset_seconds)
    except (TypeError, ValueError):
        total_seconds = 0
    next_at = event.now + timedelta(seconds=total_seconds) if total_seconds else None
    if total_seconds and next_at:
        ctx.state.set_trigger_next_run(event.rule_id, target_trigger_id, next_at)
        ctx.log(
            f"schedule_next: rule={event.rule_id}, trigger={target_trigger_id}, next={next_at.isoformat()}",
            level="DEBUG",
        )
    else:
        ctx.log(
            f"schedule_next: 未写入 next_run_at, total_seconds={total_seconds}",
            level="DEBUG",
        )
    return "continue"


async def store_state(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    """声明本规则要持久化的变量。

    引擎在规则链结束时统一回写变量,所以「只写 ``ctx.state``」不会生效(会被随后
    的全量回写覆盖)。这里把子集同时写进 ``ctx.state`` 与 ``ctx.persist_vars``,
    由引擎按它回写:``keys`` 非空时只持久化列出的键,否则持久化全部 ``ctx.vars``。
    ``keys`` 也接受单个字符串(按一个键处理)。
    """
    keys = params.get("keys")
    if isinstance(keys, str):
        keys = [keys]
    if keys:
        # 只写入**已经存在**的键。原来用 ctx.vars.get(k)（没有默认值），于是
        # 尚未产生的键会被存成 None：state.json 里多出一堆 null，下次
        # load_state 把 None 灌回 ctx.vars 后，该键就「存在」了，
        # 未产生的键若被存为 None，模板会直接渲染出字符串 "None"
        # 并发到群里。这在「extract_regex 先失败 / ai_reply 还没跑」的首轮
        # 是很常见的路径。
        stored = {k: ctx.vars[k] for k in keys if k in ctx.vars}
        absent = [k for k in keys if k not in ctx.vars]
        if absent:
            ctx.log(f"store_state: 变量尚未产生，跳过不写入: {absent}", level="DEBUG")
    else:
        stored = dict(ctx.vars)
    ctx.persist_vars = stored
    ctx.state.set_rule_vars(event.rule_id, stored)
    ctx.log(
        f"store_state: rule={event.rule_id}, keys={list(stored.keys())}",
        level="DEBUG",
    )
    return "continue"


async def load_state(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    _ = params
    stored = ctx.state.get_rule_vars(event.rule_id)
    if stored:
        ctx.vars.update(stored)
        ctx.log(
            f"load_state: rule={event.rule_id}, keys={list(stored.keys())}",
            level="DEBUG",
        )
    else:
        ctx.log(f"load_state: rule={event.rule_id}, 无持久化变量", level="DEBUG")
    return "continue"


async def random_pick(
    event: Event, ctx: AutomationContext, params: Dict[str, Any]
) -> HandlerResult:
    choices = params.get("choices") or []
    if isinstance(choices, str):
        # YAML `choices: "hello world"` 本该是列表。list("hello world") 会把它
        # 拆成单个字符，于是随机「发一条消息」变成了随机发一个字母，而日志
        # 看起来完全正常。这里退化成「把整串当成唯一选项」，并把问题说清楚。
        ctx.log(
            f"random_pick: choices 是字符串而非列表，已按单个选项处理: {choices!r}",
            level="WARNING",
        )
        choices = [choices]
    elif isinstance(choices, dict):
        ctx.log(
            "random_pick: choices 是映射而非列表，已取其值作为选项", level="WARNING"
        )
        choices = list(choices.values())
    else:
        try:
            choices = list(choices)
        except TypeError:
            ctx.log(
                f"random_pick: choices 类型不支持: {type(choices).__name__}",
                level="WARNING",
            )
            return "stop"
    if not choices:
        ctx.log("random_pick: 缺少choices", level="WARNING")
        return "stop"
    chosen = random.choice(choices)
    var = params.get("var")
    if var:
        ctx.vars[var] = chosen
        ctx.log(f"random_pick: 变量模式 {var}={chosen}", level="DEBUG")
        return "continue"
    chat_id = params.get("chat_id") or event.chat_id
    if chat_id is None:
        ctx.log("random_pick: 缺少chat_id", level="WARNING")
        return "stop"
    rendered = render_template(str(chosen), event, ctx)
    ctx.log(f"random_pick: 发送模式 chat_id={chat_id}, value={rendered}", level="DEBUG")
    await ctx.worker.send_message(chat_id, rendered)
    return "continue"


def register_builtin_handlers() -> None:
    register("send_text", send_text)
    register("reply_text", reply_text)
    register("extract_regex", extract_regex)
    register("ai_reply", ai_reply)
    register("blacklist_filter", blacklist_filter)
    register("delay", delay)
    register("forward", forward)
    register("external_forward", external_forward)
    register("server_chan", server_chan)
    register("schedule_next", schedule_next)
    register("store_state", store_state)
    register("load_state", load_state)
    register("random_pick", random_pick)
