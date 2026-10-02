import asyncio
import json
import pathlib
import sqlite3
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyrogram.types import Folder, InlineKeyboardButton, InlineKeyboardMarkup

from tg_signer.config import (
    ChooseOptionByImageAction,
    ClickKeyboardByTextAction,
    ReplyByCalculationProblemAction,
    SendTextAction,
    SignChatV3,
    SignConfigV3,
)
from tg_signer.core import (
    BaseUserWorker,
    ChatType,
    chat_has_forum_topics,
    get_client,
    readable_chat,
)
from tg_signer.sign_record_store import SignRecordStore


class TestBaseUserWorker:
    def test_initializes_defaults(self, signer_factory):
        worker = signer_factory(cls=BaseUserWorker, task_name=None)

        assert worker.task_name == "my_task"
        assert worker.context == {}
        assert pathlib.Path(worker.app.key).name == "acct"


def collect_outputs(monkeypatch, core):
    outputs = []

    def fake_print_to_user(message=""):
        outputs.append(message)

    monkeypatch.setattr(core, "print_to_user", fake_print_to_user)
    return outputs


def patch_client_methods(
    monkeypatch,
    core,
    *,
    start=None,
    stop=None,
    get_me=None,
    get_dialogs=None,
    get_folders=None,
    save_session_string=None,
    connect=None,
    disconnect=None,
):
    async def fake_connect(self):
        await asyncio.sleep(0)
        return True  # session 已授权

    async def fake_disconnect(self):
        await asyncio.sleep(0)

    async def fake_start(self):
        await asyncio.sleep(0)

    async def fake_stop(self):
        await asyncio.sleep(0)

    async def fake_get_me(self):
        await asyncio.sleep(0)
        return SimpleNamespace(id=123456)

    async def fake_get_dialogs(self, limit):
        del limit
        for _ in ():
            yield

    async def fake_get_folders(self):
        return []

    async def fake_save_session_string(self):
        await asyncio.sleep(0)

    monkeypatch.setattr(core.Client, "start", start or fake_start)
    monkeypatch.setattr(core.Client, "stop", stop or fake_stop)
    monkeypatch.setattr(core.Client, "get_me", get_me or fake_get_me)
    monkeypatch.setattr(core.Client, "get_dialogs", get_dialogs or fake_get_dialogs)
    monkeypatch.setattr(core.Client, "get_folders", get_folders or fake_get_folders)
    monkeypatch.setattr(
        core.Client,
        "save_session_string",
        save_session_string or fake_save_session_string,
    )
    monkeypatch.setattr(core.Client, "connect", connect or fake_connect)
    monkeypatch.setattr(core.Client, "disconnect", disconnect or fake_disconnect)


def setup_login_test(monkeypatch, core, dialogs):
    async def fake_get_dialogs(self, limit):
        del limit
        for chat in dialogs:
            yield SimpleNamespace(chat=chat)

    patch_client_methods(monkeypatch, core, get_dialogs=fake_get_dialogs)
    return collect_outputs(monkeypatch, core)


def test_get_client_caching(tmp_path):
    """get_client should return the same instance for the same key and different
    instances for different keys.
    """
    import tg_signer.core as core

    name = "acct"
    client1 = get_client(name=name, workdir=tmp_path)
    client2 = get_client(name=name, workdir=tmp_path)
    assert client1 is client2

    # different name -> different key -> different instance
    client3 = get_client(name="other", workdir=tmp_path)
    assert client3 is not client1

    key = str(pathlib.Path(tmp_path).joinpath(name).resolve())
    assert key in core._CLIENT_INSTANCES


def test_get_client_isolated_by_workdir(tmp_path):
    client1 = get_client(name="acct", workdir=tmp_path / "one")
    client2 = get_client(name="acct", workdir=tmp_path / "two")

    assert client1 is not client2
    assert client1.key != client2.key


@pytest.mark.parametrize(
    ("chat_type", "expected"),
    [
        pytest.param(ChatType.FORUM, "论坛群组", id="forum"),
        pytest.param(ChatType.DIRECT, "频道私信", id="direct"),
    ],
)
def test_readable_chat_supports_new_chat_types(chat_type, expected):
    chat = SimpleNamespace(
        id=-2001,
        title="test-chat",
        type=chat_type,
        username=None,
        first_name=None,
    )

    assert f"type: {expected}" in readable_chat(chat)


@pytest.mark.parametrize(
    ("chat", "expected"),
    [
        pytest.param(
            SimpleNamespace(type="private", is_forum=False),
            False,
            id="private",
        ),
        pytest.param(
            SimpleNamespace(type=None, is_forum=False),
            False,
            id="unknown",
        ),
    ],
)
def test_chat_has_forum_topics_returns_false_for_non_forum_chat(chat, expected):
    assert chat_has_forum_topics(chat) is expected


@pytest.mark.parametrize(
    "chat",
    [
        pytest.param(
            SimpleNamespace(type=ChatType.SUPERGROUP, is_forum=True),
            id="forum-supergroup",
        ),
        pytest.param(
            SimpleNamespace(type=ChatType.FORUM, is_forum=False),
            id="forum",
        ),
    ],
)
def test_chat_has_forum_topics_returns_true_for_forum_chat(chat):
    assert chat_has_forum_topics(chat) is True


def test_chat_has_forum_topics_returns_false_for_direct_chat():
    chat = SimpleNamespace(type=ChatType.DIRECT, is_forum=False)

    assert chat_has_forum_topics(chat) is False


@pytest.mark.asyncio
async def test_client_context_manager_reference_counting_and_start_stop(
    monkeypatch, tmp_path
):
    """Test that entering/exiting the async context manager updates reference
    counts, calls start only once for nested entries, and calls stop after
    the final exit. We monkeypatch start/stop to avoid network operations.
    """
    import tg_signer.core as core

    start_stop_calls = []

    async def fake_start(self):
        # small yield to ensure proper async behavior
        await asyncio.sleep(0)
        start_stop_calls.append("start")
        self._fake_started = True

    async def fake_stop(self):
        await asyncio.sleep(0)
        start_stop_calls.append("stop")
        self._fake_started = False

    monkeypatch.setattr(core.Client, "start", fake_start)
    monkeypatch.setattr(core.Client, "stop", fake_stop)

    name = "acct"
    client = get_client(
        name=name,
        workdir=tmp_path,
    )
    key = client.key
    assert len(core._CLIENT_INSTANCES) == 1
    assert key in core._CLIENT_INSTANCES

    # enter outer context
    async with client as c1:
        assert c1 is client
        # refcount should be 1
        assert core._CLIENT_REFS[key] == 1
        assert getattr(client, "_fake_started", False) is True

        # nested enter should not call start again
        async with client as c2:
            assert c2 is client
            assert core._CLIENT_REFS[key] == 2
            assert getattr(client, "_fake_started", False) is True

        # after inner exit refcount back to 1 and still started
        assert core._CLIENT_REFS[key] == 1
        assert getattr(client, "_fake_started", False) is True

    # after outer exit refcount should be 0 and stop should have been called
    assert core._CLIENT_REFS[key] == 0
    assert getattr(client, "_fake_started", False) is False

    # ensure start and stop each called exactly once
    assert start_stop_calls.count("start") == 1
    assert start_stop_calls.count("stop") == 1

    # instance should be removed from cache after stop
    assert key not in core._CLIENT_INSTANCES


@pytest.mark.asyncio
async def test_client_context_manager_ignores_connection_error_during_start(
    monkeypatch, tmp_path
):
    import tg_signer.core as core

    start_calls = 0

    async def fake_start(self):
        del self
        nonlocal start_calls
        start_calls += 1
        raise ConnectionError("temporary network issue")

    monkeypatch.setattr(core.Client, "start", fake_start)

    client = get_client(name="acct", workdir=tmp_path)
    key = client.key

    async with client as current:
        assert current is client
        assert core._CLIENT_REFS[key] == 1

    assert start_calls == 1
    assert key not in core._CLIENT_INSTANCES


@pytest.mark.asyncio
async def test_client_context_manager_ignores_connection_error_during_stop(
    monkeypatch, tmp_path
):
    import tg_signer.core as core

    stop_calls = 0

    async def fake_start(self):
        self._started = True

    async def fake_stop(self):
        del self
        nonlocal stop_calls
        stop_calls += 1
        raise ConnectionError("temporary network issue")

    monkeypatch.setattr(core.Client, "start", fake_start)
    monkeypatch.setattr(core.Client, "stop", fake_stop)

    client = get_client(name="acct", workdir=tmp_path)
    key = client.key

    async with client:
        assert core._CLIENT_REFS[key] == 1

    assert stop_calls == 1
    assert key not in core._CLIENT_INSTANCES


# ---------------------------------------------------------------------------
# 模块级状态回收：收敛到 forget_client() 这一个入口
# ---------------------------------------------------------------------------


def _patch_client_lifecycle(monkeypatch):
    import tg_signer.core as core

    async def fake_start(self):
        self._started = True

    async def fake_stop(self):
        self._started = False

    monkeypatch.setattr(core.Client, "start", fake_start)
    monkeypatch.setattr(core.Client, "stop", fake_stop)


@pytest.mark.asyncio
async def test_client_exit_reclaims_rate_limit_timestamp(monkeypatch, tmp_path):
    """引用归零即无在途调用，限流时间戳应当顺手回收。"""
    import tg_signer.core as core

    _patch_client_lifecycle(monkeypatch)

    client = get_client(name="acct", workdir=tmp_path)
    key = client.key
    async with client:
        core._API_LAST_CALL_AT[key] = 1.0

    assert key not in core._API_LAST_CALL_AT


@pytest.mark.asyncio
async def test_forget_client_clears_cache_but_keeps_the_mutex_lock(
    monkeypatch, tmp_path
):
    """模块外回收 client 状态必须走 `forget_client()`，且不能清掉互斥锁。

    判别性：若把 `_CLIENT_ASYNC_LOCKS[key]` 一并清掉，并发的 `__aenter__` 会
    各自新建一把锁、同时进入临界区，引用计数与 start()/stop() 都会被重复执行。
    """
    import tg_signer.core as core

    _patch_client_lifecycle(monkeypatch)

    client = get_client(name="acct", workdir=tmp_path)
    key = client.key
    async with client:
        assert core._CLIENT_REFS[key] == 1

    assert key in core._CLIENT_ASYNC_LOCKS

    core._API_LAST_CALL_AT[key] = 1.0
    core.forget_client(key)

    assert key not in core._CLIENT_INSTANCES
    assert key not in core._CLIENT_REFS
    assert key not in core._API_LAST_CALL_AT
    assert key in core._CLIENT_ASYNC_LOCKS


@pytest.mark.asyncio
async def test_forget_client_is_idempotent(monkeypatch, tmp_path):
    """WebUI 关闭登录会话与 TTL 回收可能都触发，重复调用必须安全。"""
    import tg_signer.core as core

    _patch_client_lifecycle(monkeypatch)

    client = get_client(name="acct", workdir=tmp_path)
    key = client.key

    core.forget_client(key)
    core.forget_client(key)

    assert key not in core._CLIENT_INSTANCES
    assert key not in core._CLIENT_REFS


@pytest.mark.asyncio
async def test_login_bootstrap_is_shared_between_concurrent_workers(
    monkeypatch, signer_factory
):
    """Concurrent workers with the same account should only perform one
    get_me/get_dialogs login bootstrap.
    """
    import tg_signer.core as core

    calls = {"get_me": 0, "get_dialogs": 0, "save_session_string": 0}

    async def fake_get_me(self):
        calls["get_me"] += 1
        await asyncio.sleep(0)
        return SimpleNamespace(id=123456)

    async def fake_get_dialogs(self, limit):
        del limit
        calls["get_dialogs"] += 1
        chat = SimpleNamespace(
            id=10001,
            title="test-chat",
            type="private",
            username=None,
            first_name="test",
            last_name=None,
        )
        yield SimpleNamespace(chat=chat)

    async def fake_save_session_string(self):
        calls["save_session_string"] += 1
        await asyncio.sleep(0)

    patch_client_methods(
        monkeypatch,
        core,
        get_me=fake_get_me,
        get_dialogs=fake_get_dialogs,
        save_session_string=fake_save_session_string,
    )

    signer1 = signer_factory(task_name="task_a")
    signer2 = signer_factory(
        task_name="task_b",
    )

    await asyncio.gather(
        signer1.login(num_of_dialogs=20, print_chat=False),
        signer2.login(num_of_dialogs=20, print_chat=False),
    )

    assert calls["get_me"] == 1
    assert calls["get_dialogs"] == 1
    assert calls["save_session_string"] == 1
    assert signer1.user.id == signer2.user.id == 123456


@pytest.mark.asyncio
@pytest.mark.parametrize("folder_selector", ["Sign", "7"])
async def test_login_loads_explicit_folder_chats(
    monkeypatch, signer_factory, folder_selector
):
    import tg_signer.core as core

    chat_a = SimpleNamespace(
        id=1001,
        title="A",
        type="private",
        username="chat_a",
        first_name="A",
        last_name=None,
    )
    chat_b = SimpleNamespace(
        id=1002,
        title="B",
        type="private",
        username="chat_b",
        first_name="B",
        last_name=None,
    )
    folder = Folder(
        id=7,
        name="Sign",
        pinned_chats=[chat_a, None],
        included_chats=[None, chat_a, chat_b],
        exclude_archived=True,
    )
    calls = {"get_dialogs": 0, "get_folders": 0}

    async def fake_get_dialogs(self, limit):
        del self, limit
        calls["get_dialogs"] += 1
        for _ in ():
            yield

    async def fake_get_folders(self):
        del self
        calls["get_folders"] += 1
        return [folder]

    patch_client_methods(
        monkeypatch,
        core,
        get_dialogs=fake_get_dialogs,
        get_folders=fake_get_folders,
    )
    outputs = collect_outputs(monkeypatch, core)
    signer = signer_factory()

    await signer.login(folder=folder_selector, print_chat=True)

    latest_chats_file = signer.get_user_dir(signer.user) / "latest_chats.json"
    latest_chats = json.loads(latest_chats_file.read_text(encoding="utf-8"))
    assert calls == {"get_dialogs": 0, "get_folders": 1}
    assert [chat["id"] for chat in latest_chats] == [1001, 1002]
    assert any("Folder: id: 7, name: Sign" in str(message) for message in outputs)


@pytest.mark.asyncio
async def test_login_rejects_folder_with_dynamic_rules(monkeypatch, signer_factory):
    import tg_signer.core as core

    folder = Folder(
        id=7,
        name="Personal",
        pinned_chats=[],
        included_chats=[],
        excluded_chats=[],
        include_contacts=True,
    )

    async def fake_get_folders(self):
        del self
        return [folder]

    patch_client_methods(monkeypatch, core, get_folders=fake_get_folders)
    signer = signer_factory()

    with pytest.raises(core.ChatFolderError, match="仅支持手动添加对话"):
        await signer.login(folder="Personal")


@pytest.mark.asyncio
async def test_login_non_interactive_rejects_missing_session(
    monkeypatch, signer_factory
):
    import tg_signer.core as core

    start_called = []

    async def fake_start(self):
        del self
        start_called.append(True)

    async def fake_connect(self):
        return False

    async def fake_disconnect(self):
        pass

    monkeypatch.setattr(core.Client, "start", fake_start)
    signer = signer_factory()
    monkeypatch.setattr(core.Client, "connect", fake_connect)
    monkeypatch.setattr(core.Client, "disconnect", fake_disconnect)

    with pytest.raises(core.errors.Unauthorized, match="请先登录"):
        await signer.login(print_chat=False)

    # 未触发 pyrogram 交互式登录提示
    assert start_called == []


@pytest.mark.asyncio
async def test_login_reuses_existing_session_without_prompt(
    monkeypatch, signer_factory
):
    import tg_signer.core as core

    patch_client_methods(monkeypatch, core)
    signer = signer_factory()

    await signer.login(print_chat=False)

    # 有效 session 被直接复用,登录成功且未走交互式提示
    assert signer.user is not None


@pytest.mark.asyncio
async def test_login_reports_available_folders_when_selection_is_missing(
    monkeypatch, signer_factory
):
    import tg_signer.core as core

    folder = Folder(id=7, name="Sign")

    async def fake_get_folders(self):
        del self
        return [folder]

    patch_client_methods(monkeypatch, core, get_folders=fake_get_folders)
    signer = signer_factory()

    with pytest.raises(core.ChatFolderError, match="7:Sign"):
        await signer.login(folder="Missing")


def test_user_signer_load_sign_record_migrates_legacy_json(signer_factory):
    signer = signer_factory(task_name="linuxdo")
    signer.user = SimpleNamespace(id=123456)
    legacy_record_file = signer.task_dir / "sign_record.json"
    legacy_record_file.write_text(
        json.dumps({"2026-03-17": "2026-03-17T06:00:00+08:00"}),
        encoding="utf-8",
    )

    records = signer.load_sign_record()

    assert records == {"2026-03-17": "2026-03-17T06:00:00+08:00"}
    assert signer.sign_record_store.load_records("linuxdo", "123456") == records


def test_user_signer_load_sign_record_logs_migration_hint(monkeypatch, signer_factory):
    signer = signer_factory(task_name="linuxdo")
    signer.user = SimpleNamespace(id=123456)
    legacy_record_file = signer.task_dir / "sign_record.json"
    legacy_record_file.write_text(
        json.dumps({"2026-03-17": "2026-03-17T06:00:00+08:00"}),
        encoding="utf-8",
    )
    messages = []

    def fake_log(message, level="INFO", **kwargs):
        del kwargs
        messages.append((level, message))

    monkeypatch.setattr(signer, "log", fake_log)

    signer.load_sign_record()

    assert any(
        level == "WARNING" and "migrate-sign-records" in message
        for level, message in messages
    )


def test_user_signer_persist_sign_record_writes_sqlite_only_by_default(signer_factory):
    signer = signer_factory(task_name="linuxdo")
    signer.user = SimpleNamespace(id=123456)
    sign_record = {}

    signer.persist_sign_record(
        sign_record,
        "2026-03-17",
        "2026-03-17T06:00:00+08:00",
    )

    assert sign_record == {"2026-03-17": "2026-03-17T06:00:00+08:00"}
    assert signer.sign_record_store.load_records("linuxdo", "123456") == sign_record
    assert not signer.sign_record_file.exists()


def test_persist_sign_record_tolerates_storage_error(monkeypatch, signer_factory):
    """记录写不进去只报警告,不能让整个签到任务停摆。

    ``sqlite3.Error`` 不是 ``OSError``,历史上会一路逃逸出 ``normal_run`` 的
    ``except (OSError, errors.Unauthorized)`` 把任务协程打死。
    """
    signer = signer_factory(task_name="linuxdo")
    signer.user = SimpleNamespace(id=123456)
    warnings: list[str] = []
    signer.log = lambda msg, level="INFO", **kwargs: warnings.append(msg)

    def boom(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    # sign_record_store 是 property,每次访问都新建实例,必须打在类上。
    monkeypatch.setattr(SignRecordStore, "upsert_record", boom)
    sign_record: dict[str, str] = {}

    signer.persist_sign_record(sign_record, "2026-03-17", "2026-03-17T06:00:00+08:00")

    assert sign_record == {"2026-03-17": "2026-03-17T06:00:00+08:00"}
    assert warnings and "database is locked" in warnings[0]


@pytest.mark.asyncio
async def test_login_skips_topics_for_non_forum_supergroup(monkeypatch, signer_factory):
    import tg_signer.core as core

    chat = SimpleNamespace(
        id=-1001,
        title="plain-supergroup",
        type=core.ChatType.SUPERGROUP,
        username=None,
        first_name=None,
        last_name=None,
        is_forum=False,
    )
    outputs = setup_login_test(monkeypatch, core, [chat])

    signer = signer_factory()
    signer.get_forum_topics = AsyncMock(return_value=[])

    await signer.login(num_of_dialogs=20, print_chat=True)

    signer.get_forum_topics.assert_not_awaited()
    assert any("plain-supergroup" in str(message) for message in outputs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chat_type", "is_forum"),
    [
        pytest.param(ChatType.SUPERGROUP, True, id="legacy-forum-supergroup"),
        pytest.param(ChatType.FORUM, False, id="forum"),
    ],
)
async def test_login_prints_topics_for_forum_chat(
    monkeypatch, signer_factory, chat_type, is_forum
):
    import tg_signer.core as core

    chat = SimpleNamespace(
        id=-1002,
        title=f"{chat_type.name.lower()}-chat",
        type=chat_type,
        username=None,
        first_name=None,
        last_name=None,
        is_forum=is_forum,
    )
    outputs = setup_login_test(monkeypatch, core, [chat])

    signer = signer_factory()
    signer.get_forum_topics = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=1,
                title="General",
                is_closed=False,
                is_pinned=False,
            )
        ]
    )

    await signer.login(num_of_dialogs=20, print_chat=True)

    signer.get_forum_topics.assert_awaited_once_with(chat.id, limit=20)
    assert any("message_thread_id: 1" in str(message) for message in outputs)


@pytest.mark.asyncio
async def test_login_skips_topics_for_direct_chat(monkeypatch, signer_factory):
    import tg_signer.core as core

    chat = SimpleNamespace(
        id=-1004,
        title="direct-chat",
        type=ChatType.DIRECT,
        username=None,
        first_name=None,
        last_name=None,
        is_forum=False,
    )
    outputs = setup_login_test(monkeypatch, core, [chat])

    signer = signer_factory()
    signer.get_forum_topics = AsyncMock(return_value=[])

    await signer.login(num_of_dialogs=20, print_chat=True)

    signer.get_forum_topics.assert_not_awaited()
    assert any("type: 频道私信" in str(message) for message in outputs)


@pytest.mark.asyncio
async def test_login_loads_forum_topics_after_dialog_fetch(monkeypatch, signer_factory):
    import tg_signer.core as core

    async def fake_get_dialogs(self, limit):
        del limit
        yield SimpleNamespace(
            chat=SimpleNamespace(
                id=-1005,
                title="forum-chat",
                type=core.ChatType.FORUM,
                username=None,
                first_name=None,
                last_name=None,
                is_forum=False,
            )
        )

    async def fake_get_forum_topics(self, chat_id, limit=20):
        del chat_id, limit
        yield SimpleNamespace(
            id=1,
            title="General",
            is_closed=False,
            is_pinned=False,
        )

    active_operation = None

    async def guarded_call(self, operation, call, **kwargs):
        del kwargs
        nonlocal active_operation
        assert active_operation is None, (
            f"nested api call detected: {active_operation} -> {operation}"
        )
        active_operation = operation
        try:
            return await call()
        finally:
            active_operation = None

    outputs = collect_outputs(monkeypatch, core)

    patch_client_methods(monkeypatch, core, get_dialogs=fake_get_dialogs)
    monkeypatch.setattr(core.Client, "get_forum_topics", fake_get_forum_topics)
    monkeypatch.setattr(core.BaseUserWorker, "_call_telegram_api", guarded_call)

    signer = signer_factory()

    await signer.login(num_of_dialogs=20, print_chat=True)

    assert any("message_thread_id: 1" in str(message) for message in outputs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "async_topic_parser",
    [False, True],
    ids=["sync-topic-parser", "async-topic-parser"],
)
async def test_client_get_forum_topics_handles_missing_top_message(
    monkeypatch, signer_factory, async_topic_parser
):
    import tg_signer._kurigram.methods as kurigram_methods
    import tg_signer.core as core

    signer = signer_factory()
    invoke_calls = []

    async def direct_call(_api_name, func):
        return await func()

    async def fake_resolve_peer(chat_id):
        return chat_id

    async def fake_invoke(query):
        invoke_calls.append(query)
        return SimpleNamespace(
            users=[],
            chats=[],
            messages=[SimpleNamespace(id=10)],
            topics=["topic-1", "topic-1-duplicate", "topic-2"],
        )

    async def fake_parse_message(_client, message, _users, _chats):
        return SimpleNamespace(
            id=message.id,
            date=datetime(2026, 3, 8, tzinfo=timezone.utc),
        )

    def parse_topic(_client, topic, messages, _users, _chats):
        if topic == "topic-1":
            return SimpleNamespace(id=1, title="A", top_message=messages[10])
        if topic == "topic-1-duplicate":
            return SimpleNamespace(id=1, title="A duplicate", top_message=messages[10])
        if topic == "topic-2":
            return SimpleNamespace(id=2, title="B", top_message=None)
        return None

    if async_topic_parser:

        async def fake_parse_topic(*args):
            return parse_topic(*args)

    else:
        fake_parse_topic = parse_topic

    monkeypatch.setattr(signer, "_call_telegram_api", direct_call)
    monkeypatch.setattr(signer.app, "resolve_peer", fake_resolve_peer)
    monkeypatch.setattr(signer.app, "invoke", fake_invoke)
    monkeypatch.setattr(kurigram_methods.types.Message, "_parse", fake_parse_message)
    monkeypatch.setattr(kurigram_methods.types.ForumTopic, "_parse", fake_parse_topic)

    topics = await signer.get_forum_topics(-100123, limit=20)

    assert isinstance(signer.app, core.Client)
    assert [topic.id for topic in topics] == [1, 2]
    assert len(invoke_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error_kind", ["timeout", "rpc"])
async def test_login_ignores_topic_lookup_failures(
    monkeypatch, signer_factory, error_kind
):
    import tg_signer.core as core

    chat = SimpleNamespace(
        id=-1003,
        title="forum-supergroup",
        type=core.ChatType.SUPERGROUP,
        username=None,
        first_name=None,
        last_name=None,
        is_forum=True,
    )
    outputs = setup_login_test(monkeypatch, core, [chat])

    signer = signer_factory()
    if error_kind == "timeout":
        error = asyncio.TimeoutError()
    else:
        error = core.errors.RPCError("boom")
    signer.get_forum_topics = AsyncMock(side_effect=error)

    await signer.login(num_of_dialogs=20, print_chat=True)

    signer.get_forum_topics.assert_awaited_once_with(chat.id, limit=20)
    assert signer.user.id == 123456
    assert not any("message_thread_id:" in str(message) for message in outputs)


@pytest.mark.asyncio
async def test_call_telegram_api_retries_floodwait(monkeypatch, signer_factory):
    import tg_signer.core as core

    monkeypatch.setattr(core, "_API_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(core, "_API_FLOODWAIT_PADDING_SECONDS", 0.0)
    monkeypatch.setattr(core, "_API_MAX_FLOODWAIT_RETRIES", 2)

    waits = []
    real_sleep = core.asyncio.sleep

    async def fake_sleep(seconds):
        waits.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    signer = signer_factory()

    called = 0

    async def flaky_api():
        nonlocal called
        called += 1
        if called == 1:
            raise core.errors.FloodWait(2)
        return "ok"

    result = await signer._call_telegram_api("test", flaky_api)

    assert result == "ok"
    assert called == 2
    assert waits == [2]


@pytest.mark.asyncio
async def test_call_telegram_api_raises_after_max_floodwait_retries(
    monkeypatch, signer_factory
):
    import tg_signer.core as core

    monkeypatch.setattr(core, "_API_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(core, "_API_FLOODWAIT_PADDING_SECONDS", 0.0)
    monkeypatch.setattr(core, "_API_MAX_FLOODWAIT_RETRIES", 1)

    waits = []
    real_sleep = core.asyncio.sleep

    async def fake_sleep(seconds):
        waits.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    signer = signer_factory()
    called = 0

    async def always_floodwait():
        nonlocal called
        called += 1
        raise core.errors.FloodWait(2)

    with pytest.raises(core.errors.FloodWait):
        await signer._call_telegram_api("test", always_floodwait)

    assert called == 2
    assert waits == [2]
    assert signer.app.key in core._API_LAST_CALL_AT


@pytest.mark.asyncio
async def test_call_telegram_api_without_floodwait_retry_raises_immediately(
    monkeypatch, signer_factory
):
    import tg_signer.core as core

    monkeypatch.setattr(core, "_API_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(core, "_API_FLOODWAIT_PADDING_SECONDS", 0.0)

    waits = []
    real_sleep = core.asyncio.sleep

    async def fake_sleep(seconds):
        waits.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    signer = signer_factory()

    async def floodwait_once():
        raise core.errors.FloodWait(3)

    with pytest.raises(core.errors.FloodWait):
        await signer._call_telegram_api(
            "test",
            floodwait_once,
            retry_on_floodwait=False,
        )

    assert waits == []
    assert signer.app.key in core._API_LAST_CALL_AT


@pytest.mark.asyncio
async def test_call_telegram_api_is_serialized_for_same_account(
    monkeypatch, signer_factory
):
    import tg_signer.core as core

    monkeypatch.setattr(core, "_API_MIN_INTERVAL_SECONDS", 0.0)

    signer1 = signer_factory(task_name="task_a")
    signer2 = signer_factory(task_name="task_b")

    active = 0
    max_active = 0

    async def critical_api():
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return "done"

    await asyncio.gather(
        signer1._call_telegram_api("critical", critical_api),
        signer2._call_telegram_api("critical", critical_api),
    )

    assert max_active == 1


@pytest.mark.asyncio
async def test_floodwait_backoff_does_not_hold_api_lock(monkeypatch, signer_factory):
    """FloodWait 退避必须在锁外等待。

    持锁退避会把同一个 client 的所有任务（包括其它 chat 的签到）串行阻塞，
    而 FloodWait 常见数百秒。同时确认限流间隔仍在锁内等待，否则并发调用会
    挤在一起打出去。
    """
    import tg_signer.core as core

    monkeypatch.setattr(core, "_API_MIN_INTERVAL_SECONDS", 10.0)
    monkeypatch.setattr(core, "_API_FLOODWAIT_PADDING_SECONDS", 0.0)
    monkeypatch.setattr(core, "_API_MAX_FLOODWAIT_RETRIES", 1)

    signer = signer_factory()
    records = []
    real_sleep = core.asyncio.sleep

    async def fake_sleep(seconds):
        records.append((seconds, core._API_ASYNC_LOCKS[signer.app.key].locked()))
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise core.errors.FloodWait(3600)
        return "ok"

    assert await signer._call_telegram_api("flood", flaky) == "ok"
    assert calls == 2
    # 第 1 次 sleep 是 FloodWait 退避，此时锁必须已释放
    assert records[0][0] == 3600.0
    assert records[0][1] is False
    # 第 2 次 sleep 是限流间隔，仍在锁内等待（并发调用继续被串行化）
    assert records[1][0] > 9
    assert records[1][1] is True


@pytest.mark.asyncio
async def test_wait_for_send_text_passes_message_thread_id(signer_factory):
    signer = signer_factory()
    signer.send_message = AsyncMock(return_value=None)
    chat = SignChatV3(
        chat_id=-1003763902761,
        message_thread_id=1,
        delete_after=10,
        actions=[SendTextAction(text="checkin")],
    )

    await signer.wait_for(chat, chat.actions[0])

    signer.send_message.assert_awaited_once_with(
        -1003763902761,
        "checkin",
        10,
        message_thread_id=1,
    )


@pytest.mark.asyncio
async def test_resolve_chat_route_key_supports_username(monkeypatch, signer_factory):
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    chat = SignChatV3(
        chat_id="@neo",
        actions=[SendTextAction(text="checkin")],
    )

    async def fake_get_chat(chat_id):
        assert chat_id == "@neo"
        return SimpleNamespace(id=-1003763902761)

    monkeypatch.setattr(signer.app, "get_chat", fake_get_chat)

    route_key = await signer.resolve_chat_route_key(chat)

    assert route_key == (-1003763902761, None)
    assert signer.context.resolved_route_keys[("@neo", None)] == route_key


@pytest.mark.asyncio
async def test_wait_for_uses_resolved_route_key_for_username(signer_factory):
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    chat = SignChatV3(
        chat_id="@neo",
        actions=[ClickKeyboardByTextAction(text="签到")],
    )
    raw_key = signer.get_route_key("@neo", None)
    resolved_key = signer.get_route_key(-1003763902761, None)
    message = SimpleNamespace(id=99, text="签到", photo=None, reply_markup=None)
    signer.context.resolved_route_keys[raw_key] = resolved_key
    signer.context.chat_messages[resolved_key][99] = message
    signer._click_keyboard_by_text = AsyncMock(return_value=True)

    await signer.wait_for(chat, chat.actions[0], timeout=0.5)

    signer._click_keyboard_by_text.assert_awaited_once_with(chat.actions[0], message)
    assert signer.context.chat_messages[resolved_key][99] is None


@pytest.mark.asyncio
async def test_wait_for_skips_consumed_message_placeholders(signer_factory):
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    chat = SignChatV3(
        chat_id=123,
        actions=[ClickKeyboardByTextAction(text="签到")],
    )
    route_key = signer.get_route_key(123, None)
    message = SimpleNamespace(
        id=100,
        text="签到",
        photo=None,
        reply_markup=None,
    )
    signer.context.chat_messages[route_key][99] = None
    signer.context.chat_messages[route_key][100] = message
    signer._click_keyboard_by_text = AsyncMock(return_value=True)

    await signer.wait_for(chat, chat.actions[0], timeout=0.5)

    signer._click_keyboard_by_text.assert_awaited_once_with(chat.actions[0], message)
    assert signer.context.chat_messages[route_key][99] is None
    assert signer.context.chat_messages[route_key][100] is None


@pytest.mark.asyncio
async def test_reply_by_calculation_problem_clicks_caption_inline_answer(
    signer_factory,
):
    signer = signer_factory()
    ai_tools = SimpleNamespace(calculate_problem=AsyncMock(return_value="8"))
    signer.get_ai_tools = lambda: ai_tools
    signer.request_callback_answer = AsyncMock(return_value=True)
    signer.send_message = AsyncMock(return_value=None)
    message = SimpleNamespace(
        id=99,
        text=None,
        caption="17 - 9 = ?",
        chat=SimpleNamespace(id=123),
        message_thread_id=1,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("8", callback_data="answer:8"),
                    InlineKeyboardButton("17", callback_data="answer:17"),
                ]
            ]
        ),
    )

    ok = await signer._reply_by_calculation_problem(
        ReplyByCalculationProblemAction(),
        message,
    )

    assert ok is True
    ai_tools.calculate_problem.assert_awaited_once()
    query = ai_tools.calculate_problem.await_args.args[0]
    assert "17 - 9 = ?" in query
    assert "可选答案" in query
    assert '"8"' in query
    assert '"17"' in query
    signer.request_callback_answer.assert_awaited_once_with(
        signer.app,
        123,
        99,
        "answer:8",
    )
    signer.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_by_calculation_problem_clicks_non_numeric_inline_answer(
    signer_factory,
):
    signer = signer_factory()
    ai_tools = SimpleNamespace(calculate_problem=AsyncMock(return_value="选项B"))
    signer.get_ai_tools = lambda: ai_tools
    signer.request_callback_answer = AsyncMock(return_value=True)
    signer.send_message = AsyncMock(return_value=None)
    message = SimpleNamespace(
        id=99,
        text=None,
        caption="请选择正确答案",
        chat=SimpleNamespace(id=123),
        message_thread_id=1,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("选项A", callback_data="answer:a"),
                    InlineKeyboardButton("选项B", callback_data="answer:b"),
                ]
            ]
        ),
    )

    ok = await signer._reply_by_calculation_problem(
        ReplyByCalculationProblemAction(),
        message,
    )

    assert ok is True
    query = ai_tools.calculate_problem.await_args.args[0]
    assert '"选项A"' in query
    assert '"选项B"' in query
    signer.request_callback_answer.assert_awaited_once_with(
        signer.app,
        123,
        99,
        "answer:b",
    )
    signer.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_by_calculation_problem_sends_caption_answer_without_keyboard(
    signer_factory,
):
    signer = signer_factory()
    ai_tools = SimpleNamespace(calculate_problem=AsyncMock(return_value="8"))
    signer.get_ai_tools = lambda: ai_tools
    signer.request_callback_answer = AsyncMock(return_value=True)
    signer.send_message = AsyncMock(return_value=None)
    message = SimpleNamespace(
        id=99,
        text=None,
        caption="17 - 9 = ?",
        chat=SimpleNamespace(id=123),
        message_thread_id=1,
        reply_markup=None,
    )

    ok = await signer._reply_by_calculation_problem(
        ReplyByCalculationProblemAction(),
        message,
    )

    assert ok is True
    ai_tools.calculate_problem.assert_awaited_once_with("17 - 9 = ?")
    signer.send_message.assert_awaited_once_with(123, "8", message_thread_id=1)
    signer.request_callback_answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_choose_option_by_image_uses_caption_and_option_index(signer_factory):
    signer = signer_factory()
    ai_tools = SimpleNamespace(choose_option_by_image=AsyncMock(return_value=1))
    signer.get_ai_tools = lambda: ai_tools
    signer.app.download_media = AsyncMock(return_value=BytesIO(b"image-bytes"))
    signer.request_callback_answer = AsyncMock(return_value=True)
    message = SimpleNamespace(
        id=99,
        text=None,
        caption="请点击图中的物品",
        chat=SimpleNamespace(id=123),
        photo=SimpleNamespace(file_id="photo-id"),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("手机", callback_data="answer:phone"),
                    InlineKeyboardButton("电视盒子", callback_data="answer:tv"),
                ]
            ]
        ),
    )

    ok = await signer._choose_option_by_image(ChooseOptionByImageAction(), message)

    assert ok is True
    signer.app.download_media.assert_awaited_once_with("photo-id", in_memory=True)
    ai_tools.choose_option_by_image.assert_awaited_once_with(
        b"image-bytes",
        "请点击图中的物品",
        [(0, "手机"), (1, "电视盒子")],
    )
    signer.request_callback_answer.assert_awaited_once_with(
        signer.app,
        123,
        99,
        "answer:tv",
    )


@pytest.mark.asyncio
async def test_choose_option_by_image_uses_previous_photo_for_split_keyboard(
    signer_factory,
):
    signer = signer_factory()
    ai_tools = SimpleNamespace(choose_option_by_image=AsyncMock(return_value=1))
    signer.get_ai_tools = lambda: ai_tools
    signer.app.download_media = AsyncMock(return_value=BytesIO(b"image-bytes"))
    signer.request_callback_answer = AsyncMock(return_value=True)
    photo_message = SimpleNamespace(
        id=98,
        text=None,
        caption=None,
        chat=SimpleNamespace(id=123),
        photo=SimpleNamespace(file_id="photo-id"),
        reply_markup=None,
    )
    button_message = SimpleNamespace(
        id=99,
        text="请选择图中的物品",
        caption=None,
        chat=SimpleNamespace(id=123),
        photo=None,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("手机", callback_data="answer:phone"),
                    InlineKeyboardButton("电视盒子", callback_data="answer:tv"),
                ]
            ]
        ),
    )

    ok = await signer._choose_option_by_image(
        ChooseOptionByImageAction(),
        button_message,
        [photo_message, button_message],
    )

    assert ok is True
    signer.app.download_media.assert_awaited_once_with("photo-id", in_memory=True)
    ai_tools.choose_option_by_image.assert_awaited_once_with(
        b"image-bytes",
        "请选择图中的物品",
        [(0, "手机"), (1, "电视盒子")],
    )
    signer.request_callback_answer.assert_awaited_once_with(
        signer.app,
        123,
        99,
        "answer:tv",
    )


@pytest.mark.asyncio
async def test_choose_option_by_image_rejects_invalid_option_index(signer_factory):
    signer = signer_factory()
    ai_tools = SimpleNamespace(choose_option_by_image=AsyncMock(return_value=9))
    signer.get_ai_tools = lambda: ai_tools
    signer.app.download_media = AsyncMock(return_value=BytesIO(b"image-bytes"))
    signer.request_callback_answer = AsyncMock(return_value=True)
    message = SimpleNamespace(
        id=99,
        text=None,
        caption="请点击图中的物品",
        chat=SimpleNamespace(id=123),
        photo=SimpleNamespace(file_id="photo-id"),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("手机", callback_data="answer:phone")]]
        ),
    )

    ok = await signer._choose_option_by_image(ChooseOptionByImageAction(), message)

    assert ok is False
    signer.request_callback_answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_message_routes_by_chat_id_and_message_thread_id(signer_factory):
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    route_key = signer.get_route_key(-1003763902761, 11)
    signer.context.sign_chats[route_key].append(
        SignChatV3(
            chat_id=-1003763902761,
            message_thread_id=11,
            actions=[SendTextAction(text="checkin")],
        )
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=-1003763902761),
        message_thread_id=11,
        id=99,
    )

    await signer._on_message(signer.app, message)

    assert signer.context.chat_messages[route_key][99] is message


@pytest.mark.asyncio
async def test_on_message_falls_back_to_non_thread_route(signer_factory):
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    fallback_key = signer.get_route_key(-1003763902761, None)
    signer.context.sign_chats[fallback_key].append(
        SignChatV3(
            chat_id=-1003763902761,
            actions=[SendTextAction(text="checkin")],
        )
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=-1003763902761),
        message_thread_id=22,
        id=100,
    )

    await signer._on_message(signer.app, message)

    assert signer.context.chat_messages[fallback_key][100] is message


@pytest.mark.asyncio
async def test_on_message_routes_username_chat_by_resolved_chat_id(signer_factory):
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    resolved_key = signer.get_route_key(-1003763902761, None)
    signer.context.sign_chats[resolved_key].append(
        SignChatV3(
            chat_id="@neo",
            actions=[SendTextAction(text="checkin")],
        )
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=-1003763902761),
        message_thread_id=None,
        id=101,
    )

    await signer._on_message(signer.app, message)

    assert signer.context.chat_messages[resolved_key][101] is message


@pytest.mark.asyncio
async def test_on_message_ignores_unexpected_chat(signer_factory):
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    message = SimpleNamespace(
        chat=SimpleNamespace(id=-1003763902761),
        message_thread_id=22,
        id=100,
    )

    await signer._on_message(signer.app, message)

    assert signer.context.chat_messages == {}


@pytest.mark.asyncio
async def test_schedule_messages_passes_message_thread_id(monkeypatch, signer_factory):
    signer = signer_factory()
    signer.user = SimpleNamespace(id=1)
    calls = []

    class DummyApp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def send_message(self, chat_id, text, **kwargs):
            calls.append({"chat_id": chat_id, "text": text, "kwargs": dict(kwargs)})
            return True

    async def direct_call(_api_name, func):
        return await func()

    signer.app = DummyApp()
    monkeypatch.setattr(signer, "_call_telegram_api", direct_call)

    await signer.schedule_messages(
        -1003763902761,
        "checkin",
        "0 6 * * *",
        next_times=1,
        random_seconds=0,
        message_thread_id=1,
    )

    assert calls[0]["kwargs"]["message_thread_id"] == 1


@pytest.mark.asyncio
async def test_get_schedule_messages_calls_chat_level_api(monkeypatch, signer_factory):
    signer = signer_factory()
    signer.user = SimpleNamespace(id=1)
    calls = []

    class DummyApp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_scheduled_messages(self, chat_id, **kwargs):
            calls.append({"chat_id": chat_id, "kwargs": dict(kwargs)})
            return []

    async def direct_call(_api_name, func):
        return await func()

    signer.app = DummyApp()
    monkeypatch.setattr(signer, "_call_telegram_api", direct_call)

    await signer.get_schedule_messages(-1003763902761)

    assert calls[0]["kwargs"] == {}


def test_normal_run_skips_username_resolution_errors_per_chat(signer_factory):
    import tg_signer.core as core

    signer = signer_factory()
    signer.user = SimpleNamespace(id=1)
    signer.context = signer.ensure_ctx()
    signer._validate_sign_at = lambda *_: "0 0 * * *"
    signer.load_sign_record = lambda: {}
    signer.persist_sign_record = lambda *_args, **_kwargs: None

    config = SignConfigV3(
        chats=[
            SignChatV3(chat_id="@bad", actions=[SendTextAction(text="bad")]),
            SignChatV3(chat_id=123456, actions=[SendTextAction(text="good")]),
        ],
        sign_at="0 0 * * *",
        sign_interval=0,
    )
    signer.load_config = lambda _cls: config

    signed_chats = []

    async def fake_sign_a_chat(chat):
        signed_chats.append(chat.chat_id)
        return True

    signer.sign_a_chat = fake_sign_a_chat

    class DummyApp:
        key = "dummy-app"

        def add_handler(self, *_args, **_kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get_chat(self, chat_id):
            raise core.errors.UsernameNotOccupied(chat_id)

    signer.app = DummyApp()

    asyncio.run(signer.normal_run(only_once=True))

    assert signed_chats == [123456]


def test_validate_sign_at_rejects_garbage(signer_factory):
    signer = signer_factory(task_name="bad_cron")
    assert signer._validate_sign_at("不是 cron") is None
    assert signer._validate_sign_at("06:00:00") == "0 6 * * *"
    assert signer._validate_sign_at("0 6 * * *") == "0 6 * * *"


def test_load_config_error_mentions_field(signer_factory):
    """坏配置要报出字段明细，而不是 unpack None 的天书。"""
    signer = signer_factory(task_name="bad_cron")
    signer.config_file.write_text(
        json.dumps(
            {"chats": [{"chat_id": 1, "actions": "nope"}], "sign_at": "0 6 * * *"}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"chats\.0\.actions"):
        signer.load_config()


# ---------------------------------------------------------------------------
# P2 修复:凭据落盘权限 / 内置 api 凭据提示 / LLM client 复用
#          引用计数回滚 / 共享消息状态 / sign_at 边界
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_session_string_restricts_permissions(tmp_path, monkeypatch):
    """session_string 等同账号登录态,落盘后必须收紧到仅属主可读写。"""
    import tg_signer.core as core

    calls = []

    def _spy(path, mode=0o600):
        calls.append((pathlib.Path(path), mode))
        return True

    class _FakeClient:
        def __init__(self, path):
            self._path = path

        @property
        def session_string_file(self):
            return self._path

        async def export_session_string(self):
            return "SESSION-STRING-SECRET"

    session_file = tmp_path / "acct.session_string"
    monkeypatch.setattr(core, "restrict_file_permissions", _spy)

    await core.Client.save_session_string(_FakeClient(session_file))

    assert session_file.read_text(encoding="utf-8") == "SESSION-STRING-SECRET"
    assert calls == [(session_file, 0o600)]


def test_get_api_config_warns_once_about_shared_builtin_credentials(monkeypatch):
    """未配置凭据时用的是所有用户共享的内置应用,必须提示一次且不刷屏。"""
    import tg_signer.core as core

    monkeypatch.delenv("TG_API_ID", raising=False)
    monkeypatch.delenv("TG_API_HASH", raising=False)
    monkeypatch.setattr(core, "_api_default_warned", False)
    warnings = []
    monkeypatch.setattr(
        core.logger,
        "warning",
        lambda message, *args, **kwargs: warnings.append(message),
    )

    for _ in range(3):
        assert core.get_api_config() == (core.DEFAULT_API_ID, core.DEFAULT_API_HASH)

    assert len(warnings) == 1, warnings
    assert "TG_API_ID" in warnings[0]


def test_get_api_config_uses_env_without_warning(monkeypatch):
    import tg_signer.core as core

    monkeypatch.setenv("TG_API_ID", "123456")
    monkeypatch.setenv("TG_API_HASH", "deadbeef")
    monkeypatch.setattr(core, "_api_default_warned", False)
    warnings = []
    monkeypatch.setattr(
        core.logger,
        "warning",
        lambda message, *args, **kwargs: warnings.append(message),
    )

    assert core.get_api_config() == (123456, "deadbeef")
    assert warnings == []


def test_get_ai_tools_reuses_one_instance(signer_factory, monkeypatch):
    """每条消息都会调 get_ai_tools:必须复用,否则每条消息泄漏一个 httpx 连接池。"""
    import tg_signer.core as core

    signer = signer_factory(task_name="ai_reuse")
    created = []

    class _FakeTools:
        def __init__(self, cfg):
            created.append(cfg)

    monkeypatch.setattr(core, "AITools", _FakeTools)
    monkeypatch.setattr(signer, "ensure_ai_cfg", lambda: {"api_key": "sk-test"})

    first = signer.get_ai_tools()
    second = signer.get_ai_tools()

    assert first is second
    assert len(created) == 1


@pytest.mark.asyncio
async def test_client_refcount_rolls_back_when_start_fails(monkeypatch, tmp_path):
    """start() 抛非 ConnectionError 时必须回滚引用计数。

    否则该 key 的计数永久停在 1:下一次 __aenter__ 会误判「已在运行」跳过
    start(),__aexit__ 还会去 stop() 一个从未启动过的 client。
    """
    import tg_signer.core as core

    async def fake_start(self):
        del self
        raise RuntimeError("start boom")

    monkeypatch.setattr(core.Client, "start", fake_start)

    client = get_client(name="acct", workdir=tmp_path)
    key = client.key

    with pytest.raises(RuntimeError):
        async with client:
            pass

    assert core._CLIENT_REFS[key] == 0


@pytest.mark.asyncio
async def test_wait_for_resets_waiting_message_when_action_raises(signer_factory):
    """动作处理抛异常时必须复位 waiting_message。

    否则 on_edited_message 针对同 id 的等待循环会永远自旋 —— 编辑事件再也不被
    处理,也不报错。
    """
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    chat = SignChatV3(chat_id=123, actions=[ClickKeyboardByTextAction(text="签到")])
    route_key = signer.get_route_key(123, None)
    message = SimpleNamespace(id=100, text="签到", photo=None, reply_markup=None)
    signer.context.chat_messages[route_key][100] = message

    async def boom(*_args, **_kwargs):
        raise RuntimeError("action boom")

    signer._click_keyboard_by_text = boom

    with pytest.raises(RuntimeError):
        await signer.wait_for(chat, chat.actions[0], timeout=0.5)

    assert signer.context.waiting_message is None


@pytest.mark.asyncio
async def test_on_edited_message_proceeds_after_action_failure(signer_factory):
    """端到端:动作失败之后编辑事件不能被卡住(旧实现会永久自旋)。"""
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    chat = SignChatV3(chat_id=123, actions=[ClickKeyboardByTextAction(text="签到")])
    route_key = signer.get_route_key(123, None)
    message = SimpleNamespace(id=100, text="签到", photo=None, reply_markup=None)
    signer.context.chat_messages[route_key][100] = message

    async def boom(*_args, **_kwargs):
        raise RuntimeError("action boom")

    signer._click_keyboard_by_text = boom
    handled = []

    async def fake_on_message(client, msg):
        handled.append(msg.id)

    signer._on_message = fake_on_message

    with pytest.raises(RuntimeError):
        await signer.wait_for(chat, chat.actions[0], timeout=0.5)

    edited = SimpleNamespace(
        id=100,
        text="edited",
        photo=None,
        reply_markup=None,
        from_user=SimpleNamespace(username="tester", id=1),
        chat=SimpleNamespace(id=123),
    )
    await asyncio.wait_for(signer.on_edited_message(None, edited), timeout=2)
    assert handled == [100]


@pytest.mark.asyncio
async def test_normal_run_rejects_unusable_sign_at(signer_factory, monkeypatch):
    """sign_at 拿不到规范化表达式时必须报配置错误。

    旧实现把 None 交给 croniter,抛出的 TypeError 不在 normal_run 的捕获集合
    里,表现成一句难懂的崩溃。
    """
    signer = signer_factory(task_name="bad_sign_at")
    signer.user = SimpleNamespace(id=123456)
    signer.load_config = lambda _cls: SignConfigV3(chats=[], sign_at="0 6 * * *")
    signer.load_sign_record = lambda: {}
    monkeypatch.setattr(signer, "_validate_sign_at", lambda _value: None)

    with pytest.raises(ValueError, match="sign_at"):
        await signer.normal_run(only_once=True)


@pytest.mark.asyncio
async def test_sign_once_persists_the_current_cycle_time(signer_factory, monkeypatch):
    """sign_once 用参数拿到本轮 now(旧实现闭包捕获外层 while 循环的变量)。"""
    import tg_signer.core as core

    signer = signer_factory(task_name="cycle_now")
    signer.user = SimpleNamespace(id=123456)
    signer.load_config = lambda _cls: SignConfigV3(
        chats=[SignChatV3(chat_id=1, actions=[SendTextAction(text="签到")])],
        sign_at="* * * * *",
        sign_interval=0,
    )
    signer.load_sign_record = lambda: {}
    persisted = []
    signer.persist_sign_record = lambda record, date, at: persisted.append((date, at))

    async def fake_sign_a_chat(chat):
        return True

    signer.sign_a_chat = fake_sign_a_chat

    async def fake_resolve(chat):
        return chat.chat_id

    signer.resolve_chat_route_key = fake_resolve

    frozen = datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(core, "get_now", lambda: frozen)

    class DummyApp:
        key = "dummy-app"

        def add_handler(self, *_args, **_kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    signer.app = DummyApp()

    await signer.normal_run(only_once=True)

    assert persisted == [(str(frozen.date()), frozen.isoformat())]


class _DummyApp:
    """驱动 normal_run 用的最小 app 替身(不触碰 Telegram)。"""

    key = "dummy-app"

    def add_handler(self, *_args, **_kwargs):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def _signer_for_run(
    signer_factory, monkeypatch, *, task_name, sign_at, now, chats=None
):
    import tg_signer.core as core

    signer = signer_factory(task_name=task_name)
    signer.user = SimpleNamespace(id=123456)
    signer.load_config = lambda _cls: SignConfigV3(
        chats=chats or [SignChatV3(chat_id=1, actions=[SendTextAction(text="签到")])],
        sign_at=sign_at,
        sign_interval=0,
    )
    monkeypatch.setattr(core, "get_now", lambda: now)
    signer.app = _DummyApp()
    return signer


@pytest.mark.asyncio
async def test_normal_run_waits_until_today_scheduled_time(signer_factory, monkeypatch):
    """早于 sign_at 启动时不能立刻签一次、到点再签一次。

    旧实现只要「今天还没有记录」就立刻签，于是 05:00 启动 + sign_at=06:00 会
    在同一天签到两次。
    """
    import tg_signer.core as core

    clock = {"now": datetime(2026, 9, 30, 5, 0, tzinfo=timezone(timedelta(hours=8)))}
    signer = _signer_for_run(
        signer_factory,
        monkeypatch,
        task_name="wait_until_due",
        sign_at="0 6 * * *",
        now=clock["now"],
    )
    monkeypatch.setattr(core, "get_now", lambda: clock["now"])

    real_sleep = core.asyncio.sleep
    signed_at = []

    class _StopLoop(Exception):
        pass

    async def fake_sleep(seconds):
        seconds = seconds or 0
        if seconds > 0:
            clock["now"] += timedelta(seconds=seconds)
            if clock["now"] > datetime(2026, 9, 30, 7, 0, tzinfo=clock["now"].tzinfo):
                raise _StopLoop
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    async def fake_sign_a_chat(chat):
        signed_at.append(clock["now"].isoformat())
        return True

    signer.sign_a_chat = fake_sign_a_chat

    with pytest.raises(_StopLoop):
        await signer.normal_run()

    assert signed_at == ["2026-09-30T06:00:00+08:00"]


@pytest.mark.asyncio
async def test_normal_run_catches_up_when_started_after_todays_time(
    signer_factory, monkeypatch
):
    """启动时已过今天的计划时刻，应当立刻补签一次（补签能力不能被改没）。"""
    clock = {"now": datetime(2026, 9, 30, 7, 0, tzinfo=timezone(timedelta(hours=8)))}
    signer = _signer_for_run(
        signer_factory,
        monkeypatch,
        task_name="catch_up",
        sign_at="0 6 * * *",
        now=clock["now"],
    )

    signed = []

    async def fake_sign_a_chat(chat):
        signed.append(clock["now"].isoformat())
        return True

    signer.sign_a_chat = fake_sign_a_chat

    await signer.normal_run(only_once=True)

    assert signed == ["2026-09-30T07:00:00+08:00"]
    assert "2026-09-30" in signer.load_sign_record()


@pytest.mark.asyncio
async def test_normal_run_signs_daily_midnight_cron(signer_factory, monkeypatch):
    """零点命中的每日 cron 必须能签到。

    把 croniter 锚在「当天 00:00」上取 ``next()`` 会得到明天的 00:00（严格晚于
    锚点），于是每天都判「今日无计划时刻」而永不签到 —— 本用例守住该回归。
    """
    clock = {"now": datetime(2026, 9, 30, 23, 0, tzinfo=timezone(timedelta(hours=8)))}
    signer = _signer_for_run(
        signer_factory,
        monkeypatch,
        task_name="midnight_cron",
        sign_at="0 0 * * *",
        now=clock["now"],
    )

    signed = []

    async def fake_sign_a_chat(chat):
        signed.append(clock["now"].isoformat())
        return True

    signer.sign_a_chat = fake_sign_a_chat

    await signer.normal_run(only_once=True)

    assert signed == ["2026-09-30T23:00:00+08:00"]


@pytest.mark.asyncio
async def test_normal_run_retries_the_round_when_every_chat_fails(
    signer_factory, monkeypatch
):
    """全部失败时不能直接睡到下一个计划时刻，应退避后重试本轮（而不是等一天）。"""
    import tg_signer.core as core

    frozen = datetime(2026, 9, 30, 7, 0, tzinfo=timezone(timedelta(hours=8)))
    signer = _signer_for_run(
        signer_factory,
        monkeypatch,
        task_name="retry_all_failed",
        sign_at="0 6 * * *",
        now=frozen,
    )

    real_sleep = core.asyncio.sleep
    attempts = []
    retry_waits = []

    class _StopLoop(Exception):
        pass

    async def fake_sleep(seconds):
        seconds = seconds or 0
        if seconds >= core._ALL_FAILED_RETRY_SECONDS:
            retry_waits.append(seconds)
            if len(retry_waits) >= 2:
                # 已观察到「失败 → 退避 → 再失败 → 再退避」，收工
                raise _StopLoop
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    async def failing_sign_a_chat(chat):
        attempts.append(1)
        raise RuntimeError("网络失败")

    signer.sign_a_chat = failing_sign_a_chat

    with pytest.raises(_StopLoop):
        await signer.normal_run()

    assert len(attempts) >= 2
    assert retry_waits == [core._ALL_FAILED_RETRY_SECONDS] * 2
    assert signer.load_sign_record() == {}


@pytest.mark.asyncio
async def test_normal_run_non_daily_cron_only_signs_on_matching_weekday(
    signer_factory, monkeypatch
):
    """非每日 cron（每周一 06:00）在周三启动时不能签，否则退化成每天签一次。"""
    import tg_signer.core as core

    # 2026-09-30 是周三，下一次命中是 2026-10-05（周一）06:00
    clock = {"now": datetime(2026, 9, 30, 8, 0, tzinfo=timezone(timedelta(hours=8)))}
    signer = _signer_for_run(
        signer_factory,
        monkeypatch,
        task_name="weekly_cron",
        sign_at="0 6 * * 1",
        now=clock["now"],
    )
    monkeypatch.setattr(core, "get_now", lambda: clock["now"])

    real_sleep = core.asyncio.sleep
    signed = []

    class _StopLoop(Exception):
        pass

    async def fake_sleep(seconds):
        seconds = seconds or 0
        if seconds > 0:
            clock["now"] += timedelta(seconds=seconds)
            if clock["now"] > datetime(2026, 10, 6, tzinfo=clock["now"].tzinfo):
                raise _StopLoop
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    async def fake_sign_a_chat(chat):
        signed.append(clock["now"].isoformat())
        return True

    signer.sign_a_chat = fake_sign_a_chat

    with pytest.raises(_StopLoop):
        await signer.normal_run()

    assert signed == ["2026-10-05T06:00:00+08:00"]


@pytest.mark.asyncio
async def test_normal_run_does_not_record_when_every_chat_fails(
    signer_factory, monkeypatch
):
    """所有 chat 都失败时不能写「今日已签到」，否则当天再也不会重试。"""
    frozen = datetime(2026, 9, 30, 6, 0, tzinfo=timezone(timedelta(hours=8)))
    signer = _signer_for_run(
        signer_factory,
        monkeypatch,
        task_name="all_failed",
        sign_at="* * * * *",
        now=frozen,
    )

    async def failing_sign_a_chat(chat):
        raise RuntimeError("网络失败")

    signer.sign_a_chat = failing_sign_a_chat

    await signer.normal_run(only_once=True)

    assert signer.load_sign_record() == {}


@pytest.mark.asyncio
async def test_normal_run_records_when_at_least_one_chat_succeeds(
    signer_factory, monkeypatch
):
    """部分成功仍要落库，否则重试会给已经成功的 chat 重复发消息。"""
    frozen = datetime(2026, 9, 30, 6, 0, tzinfo=timezone(timedelta(hours=8)))
    chats = [
        SignChatV3(chat_id=1, actions=[SendTextAction(text="签到")]),
        SignChatV3(chat_id=2, actions=[SendTextAction(text="签到")]),
    ]
    signer = _signer_for_run(
        signer_factory,
        monkeypatch,
        task_name="partial_ok",
        sign_at="* * * * *",
        now=frozen,
        chats=chats,
    )

    async def flaky_sign_a_chat(chat):
        if chat.chat_id == 1:
            raise RuntimeError("第一个 chat 失败")
        return True

    signer.sign_a_chat = flaky_sign_a_chat

    await signer.normal_run(only_once=True)

    assert "2026-09-30" in signer.load_sign_record()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record_value,task_name",
    [("2026-09-30T06:00:00", "naive_record"), ("不是时间", "broken_record")],
)
async def test_normal_run_tolerates_broken_sign_record_values(
    signer_factory, monkeypatch, record_value, task_name
):
    """历史 naive 时间戳/被改坏的记录不能让整个 run 崩掉。

    旧实现里 naive 值会在 `_next_run > now` 抛 TypeError，解析失败会抛
    ValueError，两者都不在 normal_run 的捕获集合内，表现为整个任务崩溃。
    """
    frozen = datetime(2026, 9, 30, 7, 0, tzinfo=timezone(timedelta(hours=8)))
    signer = _signer_for_run(
        signer_factory,
        monkeypatch,
        task_name=task_name,
        sign_at="0 6 * * *",
        now=frozen,
    )
    signer.load_sign_record = lambda: {"2026-09-30": record_value}

    signed = []

    async def fake_sign_a_chat(chat):
        signed.append(chat)
        return True

    signer.sign_a_chat = fake_sign_a_chat

    await signer.normal_run(only_once=True)

    # 今日已有(坏)记录：既不能崩，也不该再签一次
    assert signed == []


@pytest.mark.asyncio
async def test_wait_for_processes_message_edited_later_in_the_list(signer_factory):
    """较早的消息被编辑(队尾没变)也必须被处理。

    旧实现只比对队尾消息，机器人把较早那条编辑成带键盘的形态时会被永久忽略，
    表现为点击类签到一直等到超时。
    """
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    chat = SignChatV3(chat_id=123, actions=[ClickKeyboardByTextAction(text="签到")])
    route_key = signer.get_route_key(123, None)
    original = SimpleNamespace(id=100, text="A", photo=None, reply_markup=None)
    trailing = SimpleNamespace(id=200, text="B", photo=None, reply_markup=None)
    edited = SimpleNamespace(id=100, text="A-edited", photo=None, reply_markup=None)
    signer.context.chat_messages[route_key][100] = original
    signer.context.chat_messages[route_key][200] = trailing

    clicked = []
    original_processed = asyncio.Event()

    async def clicker(action, message):
        if message is original:
            original_processed.set()
            return False
        if message is edited:
            clicked.append(message)
            return True
        return False

    signer._click_keyboard_by_text = clicker

    task = asyncio.create_task(signer.wait_for(chat, chat.actions[0], timeout=3.0))
    # 等旧消息确实被处理过一次之后再编辑它，避免依赖固定时序
    await asyncio.wait_for(original_processed.wait(), timeout=2.0)
    signer.context.chat_messages[route_key][100] = edited
    await task

    assert clicked == [edited]


@pytest.mark.asyncio
async def test_on_message_tolerates_messages_without_from_user(signer_factory):
    """频道原生帖子没有 from_user，日志不能因此抛异常把消息丢掉。"""
    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    route_key = signer.get_route_key(-100123, None)
    signer.context.sign_chats[route_key].append(
        SignChatV3(chat_id=-100123, actions=[SendTextAction(text="签到")])
    )
    message = SimpleNamespace(
        id=1,
        text="频道公告",
        chat=SimpleNamespace(id=-100123, username="channel_username"),
        message_thread_id=None,
        from_user=None,
        photo=None,
        reply_markup=None,
    )

    await signer.on_message(None, message)

    assert signer.context.chat_messages[route_key][1] is message


# ---------------------------------------------------------------------------
# 回归：多群签到不能丢弃「还没轮到」的群的消息
# ---------------------------------------------------------------------------


def _noop_login():
    async def _f(*_args, **_kwargs):
        return None

    return _f


@pytest.mark.asyncio
async def test_later_chat_message_is_not_dropped(signer_factory, monkeypatch):
    """A 群等待期间到达的 B 群消息，必须留到轮到 B 时可用。

    回归：原来 sign_chats 是边处理边登记的，A 群等待键盘的 30s 里
    B 群的消息会因为 sign_chats 里还没有 B 而被判成「意料之外的聊天」
    直接丢弃，B 随后必然等满 timeout。
    """
    signer = signer_factory(task_name="multi_chat_buffer")
    signer.user = SimpleNamespace(id=42)
    chat_a = SignChatV3(chat_id=1, actions=[ClickKeyboardByTextAction(text="a")])
    chat_b = SignChatV3(chat_id=2, actions=[ClickKeyboardByTextAction(text="b")])
    signer.load_config = lambda _cls: SignConfigV3(
        chats=[chat_a, chat_b], sign_at="* * * * *", sign_interval=0
    )
    signer.load_sign_record = lambda: {}
    signer.persist_sign_record = lambda *a, **k: None

    b_message = SimpleNamespace(
        chat=SimpleNamespace(id=2), message_thread_id=None, id=555
    )
    buffered_when_b_started = {}

    async def fake_wait_for(chat, action, timeout=30):
        if chat.chat_id == 1:
            # A 还在等待时，B 的机器人推送了键盘回复
            await signer._on_message(signer.app, b_message)
        else:
            buffered_when_b_started["buffered"] = dict(
                signer.context.chat_messages[signer.get_route_key(2, None)]
            )
        return None

    signer.wait_for = fake_wait_for
    monkeypatch.setattr(signer, "login", _noop_login())

    await signer.normal_run(only_once=True)

    assert buffered_when_b_started["buffered"].get(555) is b_message, (
        "B 群的消息在轮到 B 之前就被丢弃了"
    )


# ---------------------------------------------------------------------------
# 回归：run-once 必须把「全部 chat 均失败」如实返回
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 回归：损坏的 .openai_config.json 不能把签到任务打崩在裸 traceback 上
# ---------------------------------------------------------------------------


def test_ensure_ai_cfg_reports_corrupt_config_clearly(signer_factory, monkeypatch):
    """损坏的 LLM 配置要报出可执行的指引，而不是抛 JSONDecodeError。"""
    signer = signer_factory(task_name="corrupt_llm")
    cfg_file = signer.workdir / ".openai_config.json"
    cfg_file.write_text('{"api_key": "sk-truncated', encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="llm-config"):
        signer.ensure_ai_cfg()


def test_ensure_ai_cfg_reports_shape_invalid_config(signer_factory, monkeypatch):
    """内容是 {} 时 pydantic ValidationError，同样要转成清晰报错。"""
    signer = signer_factory(task_name="shape_llm")
    (signer.workdir / ".openai_config.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="llm-config"):
        signer.ensure_ai_cfg()


# ---------------------------------------------------------------------------
# 回归：run-once 必须把「全部 chat 均失败」如实返回
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_once_returns_false_when_every_chat_fails(
    signer_factory, monkeypatch
):
    signer = signer_factory(task_name="run_once_fail")
    signer.user = SimpleNamespace(id=42)
    chat = SignChatV3(chat_id=1, actions=[ClickKeyboardByTextAction(text="a")])
    signer.load_config = lambda _cls: SignConfigV3(
        chats=[chat], sign_at="* * * * *", sign_interval=0
    )
    signer.load_sign_record = lambda: {}
    signer.persist_sign_record = lambda *a, **k: None

    async def boom(chat, action, timeout=30):
        raise RuntimeError("telegram unreachable")

    signer.wait_for = boom
    monkeypatch.setattr(signer, "login", _noop_login())

    assert await signer.run_once(0) is False, (
        "全部 chat 失败时 run_once 必须返回 False，CLI 才会给非 0 退出码"
    )


@pytest.mark.asyncio
async def test_run_once_returns_true_on_success(signer_factory, monkeypatch):
    signer = signer_factory(task_name="run_once_ok")
    signer.user = SimpleNamespace(id=42)
    chat = SignChatV3(chat_id=1, actions=[ClickKeyboardByTextAction(text="a")])
    signer.load_config = lambda _cls: SignConfigV3(
        chats=[chat], sign_at="* * * * *", sign_interval=0
    )
    signer.load_sign_record = lambda: {}
    signer.persist_sign_record = lambda *a, **k: None

    async def ok(chat, action, timeout=30):
        # wait_for 现在返回「动作是否真的完成」，成功必须是 True。
        return True

    signer.wait_for = ok
    monkeypatch.setattr(signer, "login", _noop_login())

    assert await signer.run_once(0) is True


# ---------------------------------------------------------------------------
# 回归：动作链「没做完」不能被当成签到成功
#   旧实现里 wait_for 成功与超时两条路径都 return None，sign_a_chat 无条件记
#   「处理完成」，sign_once 只靠异常判失败 —— 于是「机器人压根没回复、按钮
#   从没被点到」也会写入今日签到记录，run-once 退出 0，当天不再重试。
# ---------------------------------------------------------------------------


def _install_fake_clock(monkeypatch, core):
    """把 sleep / perf_counter 换成手动推进的假时钟。

    wait_for 是 ``while perf_counter() - start < timeout`` + ``sleep(0.3)`` 的
    轮询循环，用真时钟的话「30s 超时」这一条最该被测的路径要跑 30 秒。
    """
    clock = {"now": 0.0}
    real_sleep = core.asyncio.sleep

    async def fake_sleep(seconds):
        clock["now"] += seconds or 0
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(core.time, "perf_counter", lambda: clock["now"])
    return clock


@pytest.mark.asyncio
async def test_wait_for_returns_false_when_bot_never_replies(
    monkeypatch, signer_factory
):
    """回归：wait_for 的 30s 超时路径以前也 return None，与成功无法区分。

    用户可见后果：机器人没回复（被删消息、被禁言、频道静默）时，这次签到照样
    记成「今日已签到」，当天不再重试，用户完全看不出其实一次都没点成功。
    """
    import tg_signer.core as core

    _install_fake_clock(monkeypatch, core)

    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    chat = SignChatV3(chat_id=123, actions=[ClickKeyboardByTextAction(text="签到")])

    # 上下文里没有任何机器人消息：只能一路轮询到超时。
    ok = await signer.wait_for(chat, chat.actions[0], timeout=30)

    assert ok is False


@pytest.mark.asyncio
async def test_wait_for_returns_true_after_action_completes(
    monkeypatch, signer_factory
):
    """回归：成功路径必须返回 True（旧的 return None 同样无法与失败区分）。"""
    import tg_signer.core as core

    _install_fake_clock(monkeypatch, core)

    signer = signer_factory()
    signer.context = signer.ensure_ctx()
    chat = SignChatV3(chat_id=123, actions=[ClickKeyboardByTextAction(text="签到")])
    route_key = signer.get_route_key(123, None)
    message = SimpleNamespace(id=100, text="签到", photo=None, reply_markup=None)
    signer.context.chat_messages[route_key][100] = message
    signer._click_keyboard_by_text = AsyncMock(return_value=True)

    ok = await signer.wait_for(chat, chat.actions[0], timeout=30)

    assert ok is True


@pytest.mark.asyncio
async def test_sign_a_chat_returns_false_and_skips_the_rest_of_the_chain(
    signer_factory,
):
    """回归：sign_a_chat 以前没有返回值，链上任何一步没做完都算「处理完成」。

    用户可见后果：多动作配置里第一步（点开菜单）失败后，第二步依然照发，群里
    收到一半签到内容的垃圾消息，而记录里却写着当天已签到。
    """
    signer = signer_factory()
    chat = SignChatV3(
        chat_id=123,
        action_interval=0,
        actions=[SendTextAction(text="签到"), SendTextAction(text="确认")],
    )
    executed = []

    async def failed_wait_for(_chat, action, timeout=30):
        del timeout
        executed.append(action.text)
        return False

    signer.wait_for = failed_wait_for

    ok = await signer.sign_a_chat(chat)

    assert ok is False
    assert executed == ["签到"], "第一个动作没做完时不该继续执行后续动作"


@pytest.mark.asyncio
async def test_sign_a_chat_returns_true_when_every_action_completes(signer_factory):
    """回归：动作链全部走完时 sign_a_chat 必须返回 True。"""
    signer = signer_factory()
    chat = SignChatV3(
        chat_id=123,
        action_interval=0,
        actions=[SendTextAction(text="签到"), SendTextAction(text="确认")],
    )
    executed = []

    async def ok_wait_for(_chat, action, timeout=30):
        del timeout
        executed.append(action.text)
        return True

    signer.wait_for = ok_wait_for

    assert await signer.sign_a_chat(chat) is True
    assert executed == ["签到", "确认"]


@pytest.mark.asyncio
async def test_run_once_reports_failure_when_action_chain_incomplete(
    signer_factory, monkeypatch
):
    """回归：sign_once 只有 sign_a_chat 返回 True 才算这个 chat 签到成功。

    用户可见后果：动作超时（机器人没回）时 run-once 以前仍退出 0 并写入
    SQLite，cron/监控认为今天已签到，既不会重试、也查不到失败痕迹。
    """
    import tg_signer.core as core

    patch_client_methods(monkeypatch, core)

    signer = signer_factory(task_name="run_once_incomplete")
    signer.user = SimpleNamespace(id=42)
    chat = SignChatV3(chat_id=1, actions=[ClickKeyboardByTextAction(text="a")])
    signer.load_config = lambda _cls: SignConfigV3(
        chats=[chat], sign_at="* * * * *", sign_interval=0
    )
    signer.load_sign_record = lambda: {}

    async def not_completed(_chat):
        return False

    signer.sign_a_chat = not_completed
    monkeypatch.setattr(signer, "login", _noop_login())

    assert await signer.run_once(0) is False
    assert signer.sign_record_store.load_records("run_once_incomplete", "42") == {}


# ---------------------------------------------------------------------------
# 回归：没有配置任何 chat 时，绝不能记成「今日已签到」
#   旧实现是 `if succeeded or not config.chats:` —— 空列表让 `not config.chats`
#   为真，于是直接写记录并返回成功。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_chats_never_persists_a_signed_record(monkeypatch, signer_factory):
    """回归：``chats: []`` 曾被当成「今日已完成」写入签到记录。

    用户可见后果：记录页显示今日已签到、``run-once`` 退出 0、当天不再重试，
    而实际上**一条签到消息都没发**。

    现在配置层已拒绝空 ``chats``（``SignConfigV3._check_has_chats``），这里绕过
    校验直接构造对象，验证 ``sign_once`` 这一层仍有兜底。
    """
    import tg_signer.core as core

    patch_client_methods(monkeypatch, core)

    signer = signer_factory(task_name="empty_chats")
    signer.user = SimpleNamespace(id=42)
    # 用 model_construct 绕过校验，专门测运行期兜底
    config = SignConfigV3.model_construct(
        chats=[], sign_at="* * * * *", sign_interval=0, random_seconds=0
    )
    signer.load_config = lambda _cls: config
    signer.load_sign_record = lambda: {}
    monkeypatch.setattr(signer, "login", _noop_login())

    assert await signer.run_once(0) is False, "空 chats 被当成了签到成功"
    assert signer.sign_record_store.load_records("empty_chats", "42") == {}, (
        "空 chats 竟然写入了签到记录"
    )


# ---------------------------------------------------------------------------
# 回归：按钮点击被拒必须如实上报，不能无条件 return True
#   旧实现里 request_callback_answer 吞掉 BadRequest/TimeoutError 后隐式返回
#   None，而 _click_keyboard_by_text / _reply_by_calculation_problem /
#   _choose_option_by_image 三个调用方都写死 `return True`。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        pytest.param("bad-request", id="bad-request"),
        pytest.param("timeout", id="timeout"),
    ],
)
async def test_request_callback_answer_returns_false_on_rejected_click(
    monkeypatch, signer_factory, error
):
    """回归：MESSAGE_ID_INVALID / BUTTON_DATA_INVALID 这类拒绝以前被吞成 None。

    用户可见后果：按钮其实从没点中，签到却被记成成功，当天不再重试。
    """
    import tg_signer.core as core

    signer = signer_factory()

    async def direct_call(_api_name, func, **kwargs):
        del kwargs
        return await func()

    monkeypatch.setattr(signer, "_call_telegram_api", direct_call)

    if error == "bad-request":
        side_effect = core.errors.BadRequest("BUTTON_DATA_INVALID")
    else:
        side_effect = TimeoutError()
    client = SimpleNamespace(request_callback_answer=AsyncMock(side_effect=side_effect))

    ok = await signer.request_callback_answer(client, 123, 99, "answer:8")

    assert ok is False


@pytest.mark.asyncio
async def test_request_callback_answer_returns_true_on_success(
    monkeypatch, signer_factory
):
    """回归：点击成功路径必须返回 True，调用方才能判别成功/失败。"""
    signer = signer_factory()

    async def direct_call(_api_name, func, **kwargs):
        del kwargs
        return await func()

    monkeypatch.setattr(signer, "_call_telegram_api", direct_call)
    client = SimpleNamespace(request_callback_answer=AsyncMock(return_value=None))

    assert await signer.request_callback_answer(client, 123, 99, "answer:8") is True


@pytest.mark.asyncio
async def test_click_keyboard_by_text_propagates_rejected_click(signer_factory):
    """回归：点击被拒时 _click_keyboard_by_text 不能写死 return True。"""
    signer = signer_factory()
    signer.request_callback_answer = AsyncMock(return_value=False)
    message = SimpleNamespace(
        id=99,
        chat=SimpleNamespace(id=123),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("签到", callback_data="answer:sign")]]
        ),
    )

    ok = await signer._click_keyboard_by_text(
        ClickKeyboardByTextAction(text="签到"), message
    )

    assert ok is False


@pytest.mark.asyncio
async def test_reply_by_calculation_problem_propagates_rejected_click(
    signer_factory,
):
    """回归：算术题点按钮被拒时 _reply_by_calculation_problem 必须返回 False。"""
    signer = signer_factory()
    signer.get_ai_tools = lambda: SimpleNamespace(
        calculate_problem=AsyncMock(return_value="8")
    )
    signer.request_callback_answer = AsyncMock(return_value=False)
    message = SimpleNamespace(
        id=99,
        text=None,
        caption="17 - 9 = ?",
        chat=SimpleNamespace(id=123),
        message_thread_id=1,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("8", callback_data="answer:8")]]
        ),
    )

    ok = await signer._reply_by_calculation_problem(
        ReplyByCalculationProblemAction(), message
    )

    assert ok is False


@pytest.mark.asyncio
async def test_choose_option_by_image_propagates_rejected_click(signer_factory):
    """回归：图片选择题点按钮被拒时 _choose_option_by_image 必须返回 False。"""
    signer = signer_factory()
    signer.get_ai_tools = lambda: SimpleNamespace(
        choose_option_by_image=AsyncMock(return_value=0)
    )
    signer.app.download_media = AsyncMock(return_value=BytesIO(b"image-bytes"))
    signer.request_callback_answer = AsyncMock(return_value=False)
    message = SimpleNamespace(
        id=99,
        text=None,
        caption="请点击图中的物品",
        chat=SimpleNamespace(id=123),
        photo=SimpleNamespace(file_id="photo-id"),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("手机", callback_data="answer:phone")]]
        ),
    )

    ok = await signer._choose_option_by_image(ChooseOptionByImageAction(), message)

    assert ok is False


# ---------------------------------------------------------------------------
# 回归：delete_after 必须被规整成可用的秒数，删除失败不得影响签到结果
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("5", 5.0, id="numeric-string"),
        pytest.param(5, 5.0, id="int"),
        pytest.param(-3, 0.0, id="negative-clamped-to-zero"),
        pytest.param("abc", None, id="garbage-string"),
        pytest.param(None, None, id="none"),
        pytest.param(True, None, id="bool-true"),
        pytest.param(False, None, id="bool-false"),
        pytest.param(float("nan"), None, id="nan"),
        pytest.param(float("inf"), None, id="inf"),
    ],
)
def test_coerce_delete_after_normalizes_or_rejects(value, expected):
    """回归：YAML/JSON 里写成 ``delete_after: "5"`` 是常见笔误。

    用户可见后果：字符串会直接喂给 ``asyncio.sleep`` 抛 TypeError，而此时
    消息**已经发出去了** —— 一次成功的签到被改判为失败、run-once 退出 1。
    """
    import tg_signer.core as core

    assert core._coerce_delete_after(value) == expected


@pytest.mark.asyncio
async def test_delete_message_later_swallows_delete_failure():
    """回归：没有删除权限时 Telegram 返回 MESSAGE_DELETE_FORBIDDEN。

    用户可见后果：删除失败以前会一路冒泡出 send_message → sign_a_chat，把
    **成功**的签到判成失败：`run-once` 退出码 1、守护进程每 60s 重发一次
    签到消息刷屏。现在只记一条 WARNING。
    """
    import tg_signer.core as core

    logs = []

    class _FakeWorker:
        def log(self, msg, level="INFO", **kwargs):
            del kwargs
            logs.append((level, msg))

        async def _call_telegram_api(self, operation, _call, **kwargs):
            del _call, kwargs
            assert operation == "messages.DeleteMessages"
            raise core.errors.MessageDeleteForbidden("MESSAGE_DELETE_FORBIDDEN")

    message = SimpleNamespace(delete=SimpleNamespace(chat_id=1, message_ids=[9]))

    # 关键断言：不抛异常。delete_after=0 → sleep(0)，不会真的等待。
    await core._delete_message_later(_FakeWorker(), message, 0, "Message「签到」 to 1")

    assert any(
        level == "WARNING" and "MESSAGE_DELETE_FORBIDDEN" in msg for level, msg in logs
    ), logs


@pytest.mark.asyncio
async def test_send_message_succeeds_when_delete_is_forbidden(
    monkeypatch, signer_factory
):
    """回归：自动删除失败不能把已送达的消息改判成发送失败。"""
    import tg_signer.core as core

    signer = signer_factory()
    sent = SimpleNamespace(delete=SimpleNamespace(chat_id=1, message_ids=[9]))
    monkeypatch.setattr(signer.app, "send_message", AsyncMock(return_value=sent))

    async def fake_call(operation, call, **kwargs):
        del kwargs
        if operation == "messages.DeleteMessages":
            raise core.errors.MessageDeleteForbidden("MESSAGE_DELETE_FORBIDDEN")
        return await call()

    monkeypatch.setattr(signer, "_call_telegram_api", fake_call)

    message = await signer.send_message(1, "签到", 0)

    assert message is sent


# ---------------------------------------------------------------------------
# 回归：FloodWait 重试后 get_forum_topics 不能把话题列表翻倍
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_forum_topics_does_not_duplicate_after_floodwait_retry(
    monkeypatch, signer_factory
):
    """回归：累加列表以前建在重试闭包**外面**。

    ``get_forum_topics`` 是异步生成器，迭代到一半抛 FloodWait 时
    ``_call_telegram_api`` 会重新调用同一个闭包，旧代码于是把已收集的
    topic 再追加一遍（1,2,3,1,2,3）。用户可见后果：``list-topics`` 与登录
    时的 topic 预览每多一次重试就多打印一份。
    """
    import tg_signer.core as core

    monkeypatch.setattr(core, "_API_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(core, "_API_FLOODWAIT_PADDING_SECONDS", 0.0)
    monkeypatch.setattr(core, "_API_MAX_FLOODWAIT_RETRIES", 2)

    real_sleep = core.asyncio.sleep

    async def fake_sleep(seconds):
        del seconds
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    signer = signer_factory()
    attempts = {"count": 0}

    async def fake_get_forum_topics(_client, chat_id, limit=20):
        del _client, chat_id, limit
        attempts["count"] += 1
        for topic_id in (1, 2, 3):
            yield SimpleNamespace(
                id=topic_id,
                title=f"topic-{topic_id}",
                is_closed=False,
                is_pinned=False,
            )
        if attempts["count"] == 1:
            raise core.errors.FloodWait(1)

    monkeypatch.setattr(core.Client, "get_forum_topics", fake_get_forum_topics)

    topics = await signer.get_forum_topics(-100123, limit=20)

    assert attempts["count"] == 2, "第一次应当被 FloodWait 打断并重试"
    assert [topic.id for topic in topics] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 回归：每轮都要重新注册消息回调
#   pyrogram 的 Client.__aexit__ 在引用计数归零时调用 stop()，而 stop() 默认
#   clear_handlers=True → dispatcher.groups.clear()。normal_run 的 add_handler
#   写在 while True 之外，第二轮起机器人回复没有任何 handler 接手。
# ---------------------------------------------------------------------------


def test_ensure_message_handlers_is_idempotent_and_restores_after_clear(
    signer_factory,
):
    """回归：_ensure_message_handlers 幂等，且能在 handlers 被清空后补回来。

    用户可见后果：守护进程从第二轮开始收不到任何机器人消息，点击按钮 / 算术
    题 / 图片选择只能干等到 wait_for 超时，签到静默失败。
    """
    import tg_signer.core as core

    signer = signer_factory()
    handlers = [
        core.MessageHandler(signer.on_message, core.filters.chat([1])),
        core.EditedMessageHandler(signer.on_edited_message, core.filters.chat([1])),
    ]
    signer._message_handlers = handlers

    groups: dict = {}
    registered: list = []

    def add_handler(handler, group=0):
        registered.append(handler)
        groups.setdefault(group, []).append(handler)

    signer.app = SimpleNamespace(
        dispatcher=SimpleNamespace(groups=groups),
        add_handler=add_handler,
    )

    signer._ensure_message_handlers()
    assert groups.get(0) == handlers

    # 幂等：重复调用会 append 出重复回调（一条消息被处理多次）
    signer._ensure_message_handlers()
    assert groups.get(0) == handlers
    assert registered == handlers

    # 模拟 pyrogram stop() 的 dispatcher.groups.clear()
    groups.clear()
    signer._ensure_message_handlers()
    assert groups.get(0) == handlers
    assert registered == handlers * 2


@pytest.mark.asyncio
async def test_normal_run_reregisters_handlers_every_round(signer_factory, monkeypatch):
    """回归端到端：normal_run 的每一轮都要补注册回调。

    用户可见后果：守护进程跑过第一轮之后就再也收不到机器人消息，此后每一次
    点击类签到都必然等满 30s 超时，且看起来「没有任何报错」。
    """
    import tg_signer.core as core

    class _DispatcherApp:
        """模拟 pyrogram：__aexit__ 时 stop() 会清空 dispatcher.groups。"""

        key = "dummy-app"

        def __init__(self):
            self.dispatcher = SimpleNamespace(groups={})
            self.groups_at_enter: list[int] = []
            self.registered_counts: list[int] = []
            self.added: list = []

        def add_handler(self, handler, group=0):
            self.added.append(handler)
            self.dispatcher.groups.setdefault(group, []).append(handler)
            self.registered_counts.append(len(self.dispatcher.groups[group]))

        async def __aenter__(self):
            self.groups_at_enter.append(len(self.dispatcher.groups.get(0, [])))
            return self

        async def __aexit__(self, *_args):
            self.dispatcher.groups.clear()
            return None

    frozen = datetime(2026, 9, 30, 6, 0, tzinfo=timezone(timedelta(hours=8)))
    signer = _signer_for_run(
        signer_factory,
        monkeypatch,
        task_name="reregister_handlers",
        sign_at="* * * * *",
        now=frozen,
    )
    app = _DispatcherApp()
    signer.app = app

    class _StopLoop(Exception):
        pass

    real_sleep = core.asyncio.sleep
    waits = {"count": 0}

    async def fake_sleep(seconds):
        # 只在「睡到下一轮」时计数，轮询/间隔用的 0 秒照常放行；
        # 第一次跨轮 sleep 放行（进入第二轮），第二次收工。
        if seconds:
            waits["count"] += 1
            if waits["count"] >= 2:
                raise _StopLoop
        await real_sleep(0)

    monkeypatch.setattr(core.asyncio, "sleep", fake_sleep)

    async def ok_sign_a_chat(_chat):
        return True

    signer.sign_a_chat = ok_sign_a_chat

    with pytest.raises(_StopLoop):
        await signer.normal_run()

    assert app.groups_at_enter == [0, 0], "第二轮进入 client 时回调已被清空"
    # 第一轮注册 2 个、第二轮再补 2 个，且任何时刻都只有 2 个（没有重复注册）
    assert app.registered_counts == [1, 2, 1, 2]
    assert waits["count"] == 2, "本用例必须真的跑满两轮"


# ---------------------------------------------------------------------------
# 回归：stop() 抛非 ConnectionError 时 __aexit__ 的清理必须照常走完
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_exit_cleans_up_when_stop_raises_non_connection_error(
    monkeypatch, tmp_path
):
    """回归：__aexit__ 以前只 ``except ConnectionError: pass``。

    stop() → terminate() → storage.save() → sqlite commit，库被占用时抛的是
    sqlite3.OperationalError，既不是 ConnectionError 也不是 OSError：原来它
    会直接逃出 __aexit__，跳过下面两行 pop（client 与限流时间戳永久残留），
    异常再冒到 normal_run 的 ``except (OSError, errors.Unauthorized)`` 之外，
    把整个签到守护进程打死。用户可见后果：`tg-signer run` 第一次空闲就会退出。
    """
    import tg_signer.core as core

    async def fake_start(self):
        del self

    async def fake_stop(self):
        del self
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(core.Client, "start", fake_start)
    monkeypatch.setattr(core.Client, "stop", fake_stop)

    client = get_client(name="acct", workdir=tmp_path)
    key = client.key

    async with client:
        core._API_LAST_CALL_AT[key] = 1.0

    assert core._CLIENT_REFS[key] == 0
    assert key not in core._CLIENT_INSTANCES
    assert key not in core._API_LAST_CALL_AT
