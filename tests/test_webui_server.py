"""FastAPI 后端 API 冒烟测试（Vue 前后端分离改造后的服务层）。

基于 ``fastapi.testclient.TestClient`` 验证后端 REST API 的核心路径：
状态/工作目录、配置 CRUD、签到记录、用户信息、LLM 配置、账号列表、
群组缓存、运行管理、日志与鉴权。需要真实网络的端点（实时拉取对话、
发送验证码、LLM 连通性测试）不在此处执行。
"""

from __future__ import annotations

import copy
import json
import logging
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from tg_signer.webui import data as data_mod
from tg_signer.webui import server

SIGNER_PAYLOAD = {
    "chats": [
        {
            "chat_id": "@channel_or_user",
            "message_thread_id": None,
            "name": "示例任务",
            "delete_after": None,
            "actions": [{"action": 1, "text": "签到"}],
            "action_interval": 1,
        }
    ],
    "sign_at": "0 6 * * *",
    "random_seconds": 0,
    "sign_interval": 1,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """每个测试使用独立工作目录，并在临时目录中启动应用。"""
    # 可切换的工作目录默认只含初始工作目录的父目录，这里显式放开到 tmp_path。
    monkeypatch.setenv(data_mod.WORKDIR_ROOTS_ENV, str(tmp_path))
    server.state.set_workdir(str(tmp_path))
    with TestClient(server.app) as test_client:
        yield test_client


def test_state_roundtrip(client, tmp_path):
    resp = client.get("/api/state")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["workdir"] == str(tmp_path)
    assert payload["auth_required"] is False
    assert payload["log_path"].endswith("tg-signer.log")


def test_state_switch_workdir(client, tmp_path):
    target = tmp_path / "other"
    resp = client.post("/api/state", json={"workdir": str(target)})
    assert resp.status_code == 200
    assert resp.json()["workdir"] == str(target)


def test_switch_workdir_rebinds_log_file_to_new_dir(client, tmp_path, monkeypatch):
    """基础设置显示的「主日志路径」必须是日志真正写入的位置。

    日志 handler 在进程启动时按当时的 workdir 绑定；切换工作目录后
    /api/state 报的是新路径，日志却仍写进旧目录，新目录的 logs/ 甚至不会被
    创建 —— 页面显示的路径成了假路径，切到全新目录时日志页直接空白。
    """
    old_log = tmp_path / "logs" / data_mod.LOG_FILE_NAME
    assert old_log.parent.is_dir(), "前置条件：启动时应已建好旧 logs 目录"

    target = tmp_path / "other"
    resp = client.post("/api/state", json={"workdir": str(target)})
    assert resp.status_code == 200
    reported = pathlib.Path(resp.json()["log_path"])

    # configure_logger 的默认 logger 名是 "tg-signer"（连字符）。
    logger = logging.getLogger("tg-signer")
    logger.warning("probe-after-switch")
    for handler in logger.handlers:
        handler.flush()

    assert reported == target / "logs" / data_mod.LOG_FILE_NAME
    assert reported.parent.is_dir(), f"切换后 logs 目录未创建: {reported}"
    assert reported.read_text(encoding="utf-8", errors="ignore"), "日志没有写进新目录"


@pytest.mark.parametrize(
    "relative",
    ["../wb_outside_a", "../../wb_outside_b", "../wb_outside_c/nested"],
)
def test_state_rejects_workdir_outside_allowed_roots(client, tmp_path, relative):
    """白名单之外的目录必须被拒，且不能被 mkdir 创建出来。"""
    outside = (tmp_path / relative).resolve()
    resp = client.post("/api/state", json={"workdir": str(outside)})
    assert resp.status_code == 400, resp.json()
    assert "越界" in resp.json()["detail"]
    assert not outside.exists()
    # 失败后工作目录保持不变
    assert client.get("/api/state").json()["workdir"] == str(tmp_path)


def test_config_template(client):
    signer_tpl = client.get("/api/configs/signer/template")
    assert signer_tpl.status_code == 200
    assert "chats" in signer_tpl.json()["payload"]

    assert client.get("/api/configs/unknown/template").status_code == 400


def test_save_config_rejects_invalid_cron_with_field_detail(client):
    payload = {**SIGNER_PAYLOAD, "sign_at": "不是 cron"}
    resp = client.post("/api/configs/signer/bad_cron", json=payload)
    assert resp.status_code == 400
    assert "sign_at" in resp.json()["detail"]


def test_save_config_reports_offending_field(client):
    payload = copy.deepcopy(SIGNER_PAYLOAD)
    payload["chats"][0]["actions"] = "not-a-list"
    resp = client.post("/api/configs/signer/bad_action", json=payload)
    assert resp.status_code == 400
    assert "chats.0.actions" in resp.json()["detail"]


def test_save_automation_reports_offending_field(client):
    resp = client.post(
        "/api/configs/automation/bad_rule",
        json={
            "rules": [
                {
                    "id": "r1",
                    "enabled": True,
                    "triggers": [
                        {"type": "message", "params": {"chat_id": 123, "nope": 1}}
                    ],
                    "handlers": [{"handler": "send_text", "params": {"text": "hi"}}],
                }
            ]
        },
    )
    assert resp.status_code == 400
    assert "nope" in resp.json()["detail"]


def test_config_suggest_name(client):
    resp = client.get(
        "/api/configs/signer/suggest-name",
        params={"chat_id": "-1001234567890", "title": "My Group"},
    )
    assert resp.status_code == 200
    name = resp.json()["name"]
    assert name.startswith("sign_My_Group_")

    # 无标题时退回用 chat_id 兜底，且缺省参数也要能工作
    fallback = client.get("/api/configs/signer/suggest-name").json()["name"]
    assert fallback.startswith("sign_")

    # 无标题但有用户名时，用用户名而不是数字 ID 兜底
    by_user = client.get(
        "/api/configs/signer/suggest-name",
        params={"chat_id": "-1001234567890", "username": "my_group"},
    ).json()["name"]
    assert by_user.startswith("sign_my_group_")

    assert client.get("/api/configs/unknown/suggest-name").status_code == 400


def test_config_suggest_name_supports_automation(client):
    resp = client.get(
        "/api/configs/automation/suggest-name",
        params={"chat_id": "-1001234567890", "title": "My Group"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"].startswith("auto_My_Group_")


def test_configs_crud(client):
    resp = client.post("/api/configs/signer/demo", json=SIGNER_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["name"] == "demo"

    assert client.get("/api/configs/signer").json()["names"] == ["demo"]

    got = client.get("/api/configs/signer/demo")
    assert got.status_code == 200
    payload = got.json()["payload"]
    assert payload["sign_at"] == "0 6 * * *"
    assert payload["chats"][0]["chat_id"] == "@channel_or_user"

    assert client.get("/api/configs/signer/missing").status_code == 404
    assert client.get("/api/configs/unknown").status_code == 400

    assert client.delete("/api/configs/signer/demo").json()["ok"] is True
    assert client.get("/api/configs/signer").json()["names"] == []


def test_configs_list_automation_names(client, tmp_path):
    (tmp_path / "automations" / "daily").mkdir(parents=True)
    (tmp_path / "automations" / "daily" / "config.json").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / "automations" / "nightly").mkdir(parents=True)
    (tmp_path / "automations" / "nightly" / "config.yaml").write_text(
        "rules: []", encoding="utf-8"
    )
    # 残留空目录不应被列出
    (tmp_path / "automations" / "ghost").mkdir(parents=True)

    resp = client.get("/api/configs/automation")
    assert resp.status_code == 200
    assert resp.json()["names"] == ["daily", "nightly"]


def test_automation_config_crud_via_api(client, tmp_path):
    tpl = client.get("/api/configs/automation/template")
    assert tpl.status_code == 200
    assert tpl.json()["payload"]["rules"][0]["id"] == "demo_message_reply"

    payload = {
        "rules": [
            {
                "id": "rule_1",
                "triggers": [{"type": "message", "params": {"chat_id": "@chan"}}],
                "handlers": [{"handler": "send_text", "params": {"text": "ok"}}],
            }
        ]
    }
    resp = client.post("/api/configs/automation/demo", json=payload)
    assert resp.status_code == 200
    assert resp.json()["name"] == "demo"
    assert (tmp_path / "automations" / "demo" / "config.json").is_file()

    got = client.get("/api/configs/automation/demo")
    assert got.status_code == 200
    assert got.json()["payload"]["rules"][0]["id"] == "rule_1"

    assert client.get("/api/configs/automation/missing").status_code == 404
    bad = client.post(
        "/api/configs/automation/bad",
        json={"rules": [{"id": "no_triggers"}]},
    )
    assert bad.status_code == 400

    assert client.delete("/api/configs/automation/demo").json()["ok"] is True
    assert client.get("/api/configs/automation").json()["names"] == []


def test_records_and_users_empty(client):
    assert client.get("/api/records").json() == []
    assert client.get("/api/users").json() == []


def test_llm_config_roundtrip(client, monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = client.post(
        "/api/llm-config",
        json={
            "api_key": "sk-test-abcdefgh",
            "base_url": "https://example.com/v1",
            "model": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 200

    payload = client.get("/api/llm-config").json()
    assert payload["has_env"] is False
    # 明文密钥不回显，只给尾部 4 位的掩码
    assert payload["config"]["api_key"] == "****efgh"
    assert "sk-test-abcdefgh" not in resp.text
    assert payload["config"]["base_url"] == "https://example.com/v1"
    assert payload["config"]["model"] == "gpt-4o-mini"

    stored = (tmp_path / ".openai_config.json").read_text(encoding="utf-8")
    assert "sk-test-abcdefgh" in stored


def test_llm_config_rejects_empty_key(client):
    resp = client.post("/api/llm-config", json={"api_key": "   "})
    assert resp.status_code == 400


def test_llm_config_keeps_stored_key_when_blank_or_masked(client, tmp_path):
    """留空或原样回显掩码都表示「不修改密钥」，只更新其余字段。"""
    client.post("/api/llm-config", json={"api_key": "sk-keep-12345678"})

    for posted in ("", "****5678"):
        resp = client.post(
            "/api/llm-config",
            json={"api_key": posted, "base_url": "https://changed/v1"},
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["api_key_unchanged"] is True

    config = json.loads((tmp_path / ".openai_config.json").read_text("utf-8"))
    assert config["api_key"] == "sk-keep-12345678"
    assert config["base_url"] == "https://changed/v1"


def test_llm_config_replaces_key_when_new_value_posted(client, tmp_path):
    client.post("/api/llm-config", json={"api_key": "sk-old-12345678"})

    resp = client.post("/api/llm-config", json={"api_key": "sk-new-87654321"})
    assert resp.status_code == 200
    assert resp.json()["api_key_unchanged"] is False

    config = json.loads((tmp_path / ".openai_config.json").read_text("utf-8"))
    assert config["api_key"] == "sk-new-87654321"


def test_llm_config_test_endpoint_falls_back_to_stored_key(client, monkeypatch):
    """前端回显掩码 / 留空时，连通性测试必须用服务端保存的真实密钥。"""
    client.post("/api/llm-config", json={"api_key": "sk-stored-87654321"})

    seen = {}

    async def fake_test(api_key, base_url=None, model=None):
        seen["api_key"] = api_key
        return True, "ok"

    monkeypatch.setattr(server, "test_openai_connection", fake_test)

    for posted in ("", "****4321"):
        resp = client.post("/api/llm-config/test", json={"api_key": posted})
        assert resp.status_code == 200, resp.json()
        assert seen["api_key"] == "sk-stored-87654321"

    resp = client.post("/api/llm-config/test", json={"api_key": "sk-typed-00000000"})
    assert resp.status_code == 200
    assert seen["api_key"] == "sk-typed-00000000"


def test_accounts_list_and_authorized(client, tmp_path):
    assert client.get("/api/accounts").json() == []

    (tmp_path / "acc.session").write_text("x", encoding="utf-8")
    accounts = client.get("/api/accounts").json()
    assert [item["account"] for item in accounts] == ["acc"]

    resp = client.get("/api/accounts/acc/authorized")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = client.get("/api/accounts/ghost/authorized")
    assert resp.json()["ok"] is False


def test_chats_cache_empty(client):
    assert client.get("/api/chats").json() == []


def test_run_status_and_controls(client):
    assert client.get("/api/run").json() == {"tasks": {}, "task_names": {}}

    resp = client.post(
        "/api/run/start",
        json={"kind": "signer", "tasks": [], "account": "acc"},
    )
    assert resp.json()["ok"] is False
    assert "任务名" in resp.json()["message"]

    resp = client.post("/api/run/stop", json={"kind": "signer", "account": "acc"})
    assert resp.json()["ok"] is False
    assert "未在运行" in resp.json()["message"]


def test_logs(client, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "tg-signer.log").write_text("line1\nline2", encoding="utf-8")

    resp = client.get("/api/logs")
    assert resp.status_code == 200
    payload = resp.json()
    assert str(payload["path"]).endswith("tg-signer.log")
    assert payload["lines"] == ["line1", "line2"]

    files = client.get("/api/logs/files").json()["files"]
    assert any(str(f).endswith("tg-signer.log") for f in files)


# ---------------------------------------------------------------------------
# 越权 / 路径穿越（负向用例）
#
# 历史上 `/api/logs?path=` 是任意文件读取原语（能读到 *.session_string 与
# .openai_config.json），`account` 与配置名则未归一化，可越界创建 / 删除文件。
# ---------------------------------------------------------------------------


def test_logs_rejects_path_outside_log_dir(client, tmp_path):
    """只有 <workdir>/logs 下的文件可读，其余一律 400。"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "tg-signer.log").write_text("real\n", encoding="utf-8")

    # workdir 根目录下的敏感文件（session / LLM key 都在这一层）
    secret = tmp_path / "acc.session_string"
    secret.write_text("SESSION-STRING-SECRET\n", encoding="utf-8")
    # workdir 之外的文件
    outside = tmp_path.parent / "tg_signer_audit_outside.log"
    outside.write_text("OUTSIDE-SECRET\n", encoding="utf-8")

    for target in (secret, outside, log_dir / ".." / "acc.session_string"):
        resp = client.get("/api/logs", params={"path": str(target)})
        assert resp.status_code == 400, f"{target} 未被拦截: {resp.json()}"
        assert "SESSION-STRING-SECRET" not in resp.text
        assert "OUTSIDE-SECRET" not in resp.text


def test_logs_accepts_file_name_and_absolute_path_inside_log_dir(client, tmp_path):
    """前端会回传 /api/logs/files 给出的绝对路径，这条正常路径必须仍然可用。"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    main_log = log_dir / "tg-signer.log"
    main_log.write_text("line1\nline2", encoding="utf-8")

    listed = client.get("/api/logs/files").json()["files"]
    assert str(main_log) in listed

    for value in ("tg-signer.log", str(main_log)):
        resp = client.get("/api/logs", params={"path": value})
        assert resp.status_code == 200, resp.json()
        assert resp.json()["lines"] == ["line1", "line2"]


def test_logs_expose_task_logs_from_subdirectories(client, tmp_path):
    """runner.py 按 <kind>-<account> 分子目录写日志，列表与读取都必须覆盖它。

    历史上 list_log_files() 用 glob 而非 rglob，且读取走只允许直接子项的
    resolve_within()，导致任务日志既列不出来也读不到，日志页只剩一个 0 字节的
    主日志顶着，表现为「整页空白」。
    """
    log_dir = tmp_path / "logs"
    (log_dir / "signer-demo").mkdir(parents=True, exist_ok=True)
    (log_dir / "tg-signer.log").write_text("", encoding="utf-8")
    task_log = log_dir / "signer-demo" / "tg-signer.log"
    task_log.write_text("task line\n", encoding="utf-8")

    listed = client.get("/api/logs/files").json()["files"]
    # 能列出来，且排在 0 字节主日志之前（前端取第一个作为默认选中项）。
    assert listed[0] == str(task_log)

    resp = client.get("/api/logs", params={"path": str(task_log)})
    assert resp.status_code == 200, resp.json()
    assert "task line" in resp.json()["lines"]


def test_logs_work_with_relative_workdir(client, tmp_path, monkeypatch):
    """默认 workdir 是相对的 ``.signer``，这正是线上 400 的触发条件。

    之前 get_workdir() 原样返回相对路径，UIState.log_path 变成
    ``.signer/logs/tg-signer.log``；前端把它回传给 /api/logs，
    resolve_log_under() 按「相对 logs/ 根目录」再次拼接 → 必然越界 → 400
    → 页面空白。已有用例都传绝对路径 tmp_path，所以从未覆盖到这条路径。
    """
    monkeypatch.chdir(tmp_path)
    server.state.set_workdir(".signer")

    log_dir = tmp_path / ".signer" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "tg-signer.log").write_text("", encoding="utf-8")
    task_log = log_dir / "signer-demo" / "tg-signer.log"
    task_log.parent.mkdir(parents=True, exist_ok=True)
    task_log.write_text("task line\n", encoding="utf-8")

    listed = client.get("/api/logs/files").json()["files"]
    assert listed, "相对 workdir 下也必须能列到日志"
    for item in listed:
        assert item == str(pathlib.Path(item).resolve()), f"返回了相对路径: {item}"
        resp = client.get("/api/logs", params={"path": item})
        assert resp.status_code == 200, f"{item} 读取失败: {resp.json()}"

    # 不指定 path 的默认读取也必须落到有内容的文件上。
    assert "task line" in client.get("/api/logs").json()["lines"]


_ACCOUNT_TRAVERSAL = ["../victim", "..\\victim", "..", ".", "", "a/b"]


@pytest.mark.parametrize("account", _ACCOUNT_TRAVERSAL)
def test_account_endpoints_reject_traversal(client, tmp_path, account):
    """account 不是单一路径分量时必须 400，不能越界建 / 删 session 文件。"""
    victim = tmp_path.parent / "victim.session"
    victim.write_text("x", encoding="utf-8")

    for resp in (
        client.post("/api/accounts/logout", json={"account": account}),
        client.post(
            "/api/accounts/send-code", json={"account": account, "phone": "+1"}
        ),
        client.post("/api/chats/fetch", json={"account": account}),
    ):
        assert resp.status_code == 400, f"{account!r} 未被拦截: {resp.json()}"
        assert "名称非法" in resp.json()["detail"]

    assert victim.is_file()


def test_run_start_rejects_traversal_and_creates_nothing_outside(client, tmp_path):
    """run/start 的 account 穿越必须被拒，且不得在 workdir 之外留下锁文件。"""
    resp = client.post(
        "/api/run/start",
        json={"kind": "signer", "tasks": ["t"], "account": "../evil"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "名称非法" in resp.json()["message"]
    assert sorted(p.name for p in tmp_path.parent.glob("evil.lock")) == []


def test_config_endpoints_do_not_touch_outside_workdir(client, tmp_path):
    """配置名穿越时不能被删除 / 写穿到 workdir 之外。

    URL 里的 `..` 会被路由层先吃掉(405/404),彻底绕过路由的写法由
    `test_webui_data.py` 在数据层逐名覆盖;这里保证的是「无论返回什么状态码,
    workdir 之外都不会产生或丢失文件」。
    """
    for name in ("../victim", "..%2F..%2Fvictim", "evil"):
        resp = client.delete(f"/api/configs/signer/{name}")
        assert resp.status_code >= 400, resp.json()

    outside = tmp_path.parent / "victim"
    assert not outside.exists()
    assert not (tmp_path.parent / "evil").exists()


def test_auth_required_when_env_set(client, monkeypatch):
    monkeypatch.setenv(server.AUTH_CODE_ENV, "secret123")

    resp = client.get("/api/state")
    assert resp.status_code == 401

    resp = client.get("/api/state", headers={"Authorization": "Bearer secret123"})
    assert resp.status_code == 200


def test_auth_login_flow(client, monkeypatch):
    monkeypatch.setenv(server.AUTH_CODE_ENV, "secret123")

    assert client.get("/api/auth/status").json()["required"] is True

    bad = client.post("/api/auth/login", json={"code": "wrong"})
    assert bad.json()["ok"] is False

    good = client.post("/api/auth/login", json={"code": "secret123"})
    assert good.json()["ok"] is True


@pytest.fixture()
def reset_auth_storage():
    """失败计数是模块级全局状态，鉴权用例前后都要清干净以免互相污染。"""
    with server._auth_storage_lock:
        server._auth_storage.clear()
    yield
    with server._auth_storage_lock:
        server._auth_storage.clear()


def _lock_held() -> bool:
    """当前线程是否已持有 ``_auth_storage_lock``。

    ``threading.Lock`` 不可重入，被本线程持有时 ``acquire(blocking=False)``
    返回 ``False``，据此可以确定被调用的那一刻锁是否在手上。
    """
    acquired = server._auth_storage_lock.acquire(blocking=False)
    if acquired:
        server._auth_storage_lock.release()
    return not acquired


def test_auth_login_records_failure_under_lock(client, monkeypatch, reset_auth_storage):
    """失败计数必须在锁内完成读-改-写，否则并发请求会把锁定次数冲掉。"""
    monkeypatch.setenv(server.AUTH_CODE_ENV, "secret123")
    observed = []
    real = server.auth_helpers.record_auth_failure

    def spy(storage):
        observed.append(_lock_held())
        return real(storage)

    monkeypatch.setattr(server.auth_helpers, "record_auth_failure", spy)

    resp = client.post("/api/auth/login", json={"code": "wrong"})
    assert resp.json()["ok"] is False
    assert observed == [True], "record_auth_failure 未在锁内调用"


def test_auth_login_clears_failures_under_lock(client, monkeypatch, reset_auth_storage):
    monkeypatch.setenv(server.AUTH_CODE_ENV, "secret123")
    observed = []
    real = server.auth_helpers.clear_auth_failures

    def spy(storage):
        observed.append(_lock_held())
        return real(storage)

    monkeypatch.setattr(server.auth_helpers, "clear_auth_failures", spy)

    resp = client.post("/api/auth/login", json={"code": "secret123"})
    assert resp.json()["ok"] is True
    assert observed == [True], "clear_auth_failures 未在锁内调用"


def test_auth_login_locks_out_after_max_attempts(
    client, monkeypatch, reset_auth_storage
):
    """连续错误到上限后，错误凭据开始 429；正确凭据不受锁定期影响。

    旧版这里断言「锁定期内正确授权码也 429」—— 那正是把锁定变成
    未认证者可用 DoS 原语（先锁后验）的语义，已在审计 P2-19 中推翻。
    """
    monkeypatch.setenv(server.AUTH_CODE_ENV, "secret123")
    for _ in range(server.auth_helpers.AUTH_MAX_ATTEMPTS - 1):
        resp = client.post("/api/auth/login", json={"code": "wrong"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    # 触发上限的那次请求直接 429（旧实现要到下一次才 429）。
    locked = client.post("/api/auth/login", json={"code": "wrong"})
    assert locked.status_code == 429
    assert "尝试次数过多" in locked.json()["detail"]

    # 锁定期内：不带凭据 / 带错误凭据仍然 429。
    assert client.get("/api/state").status_code == 429

    # 锁定期内：正确 Bearer 必须照常放行（先验后锁）。
    assert (
        client.get(
            "/api/state", headers={"Authorization": "Bearer secret123"}
        ).status_code
        == 200
    )

    # 锁定期内：正确授权码登录放行，并清空失败计数解除锁定。
    good_login = client.post("/api/auth/login", json={"code": "secret123"})
    assert good_login.status_code == 200
    assert good_login.json()["ok"] is True
    assert client.get("/api/state").status_code == 401  # 锁已解除，回到未认证


def test_protected_endpoints_record_auth_failures(
    client, monkeypatch, reset_auth_storage
):
    """爆破防护必须覆盖受保护端点，而不是只有 /api/auth/login。

    修复前：require_auth 只检查锁定、从不记账，攻击者改打任意受保护端点
    携带猜测的 Bearer 即可完全绕开限流（实测 30 次错误请求无一被锁）。
    """
    monkeypatch.setenv(server.AUTH_CODE_ENV, "secret123")
    attempts = server.auth_helpers.AUTH_MAX_ATTEMPTS
    statuses = [
        client.get(
            "/api/state", headers={"Authorization": f"Bearer guess{i}"}
        ).status_code
        for i in range(attempts + 1)
    ]
    # 前 4 次正常 401；第 5 次（触发上限）起开始 429。
    assert statuses[: attempts - 1] == [401] * (attempts - 1)
    assert statuses[-2:] == [429, 429], "受保护端点上的错误凭据必须参与失败计数"


def test_correct_credential_is_exempt_from_lockout(
    client, monkeypatch, reset_auth_storage
):
    """「先验后锁」的核心承诺：正确凭据永远可用，锁定只约束错误凭据。"""
    monkeypatch.setenv(server.AUTH_CODE_ENV, "secret123")
    for _ in range(server.auth_helpers.AUTH_MAX_ATTEMPTS):
        client.post("/api/auth/login", json={"code": "wrong"})

    resp = client.get("/api/state", headers={"Authorization": "Bearer secret123"})
    assert resp.status_code == 200, "正确 Bearer 不应受锁定期影响"


def test_non_ascii_authorization_header_is_rejected_not_crash(
    monkeypatch, reset_auth_storage
):
    """secrets.compare_digest 对含非 ASCII 的 str 会抛 TypeError（→ 500）。

    因此比较前必须编码成 bytes：授权码本身可能包含任意字符，攻击者也可能
    在 Authorization 头里塞非 ASCII。（httpx 客户端无法发送非 ASCII 头，
    故直接调用 require_auth 验证服务端行为。）
    """
    monkeypatch.setenv(server.AUTH_CODE_ENV, "secret123")
    with pytest.raises(server.HTTPException) as exc_info:
        server.require_auth(authorization="Bearer 密码")
    assert exc_info.value.status_code == 401


def test_index_disables_cache_and_assets_are_immutable(client):
    """index.html 必须回源校验，带 hash 的 chunk 才可长期缓存。

    历史问题：两者都没发 Cache-Control，浏览器按 Last-Modified 做启发式
    缓存。升级后 Vite 会重命名 chunk（如 Configs-D3OhaQpj.js ->
    Configs-DeKRQTYv.js），被缓存的旧 index.html 仍指向已删除的 chunk，
    入口 JS 404 导致整页白屏。
    """
    resp = client.get("/")
    if resp.status_code == 200:
        assert "no-cache" in resp.headers.get("cache-control", "")

    static_dir = pathlib.Path(server.__file__).parent / "static"
    index_html = static_dir / "index.html"
    if not index_html.exists():
        pytest.skip("前端尚未构建，缺少 static/index.html")

    entry_match = re.search(
        r"assets/(index-[A-Za-z0-9_-]+\.js)", index_html.read_text(encoding="utf-8")
    )
    assert entry_match, "index.html 未引用入口 chunk"

    asset = client.get(f"/assets/{entry_match.group(1)}")
    if asset.status_code == 200:
        assert "immutable" in asset.headers.get("cache-control", "")


def test_index_served_or_reports_missing_build(client):
    resp = client.get("/")
    assert resp.status_code in (200, 503)


def test_static_assets_referenced_by_entry_are_committed():
    """前端产物随仓库分发，入口 chunk 引用的资源必须一起提交。

    历史问题：入口 bundle 的 __vite__mapDeps 引用了未提交的 chunk，
    线上加载 Login 视图时动态 import 404，页面渲染为空白。
    """
    static_dir = pathlib.Path(server.__file__).parent / "static"
    index_html = static_dir / "index.html"
    if not index_html.exists():
        pytest.skip("前端尚未构建，缺少 static/index.html")

    html = index_html.read_text(encoding="utf-8")
    entry_match = re.search(r"assets/(index-[A-Za-z0-9_-]+\.js)", html)
    assert entry_match, "index.html 未引用入口 chunk"

    entry = static_dir / "assets" / entry_match.group(1)
    assert entry.exists(), f"入口 chunk 缺失: {entry.name}"

    bundle = entry.read_text(encoding="utf-8")
    referenced = set(re.findall(r'"assets/([^"]+)"', bundle))
    assert referenced, "入口 chunk 未声明预加载依赖"

    missing = sorted(
        name for name in referenced if not (static_dir / "assets" / name).exists()
    )
    assert not missing, f"以下静态资源被入口 chunk 引用但未提交: {missing}"


def test_llm_config_ui_leaves_the_stored_key_blank():
    """前端产物必须体现「已配置，留空表示不修改」。

    服务端只回掩码（如 ``****1234``），明文不出服务端；前端若把掩码当值回填进
    密码框，用户就分不清「已配置」与「这是真实密钥」，``show-password`` 一开还会
    露出一串形如坏掉的 ``****1234``。源码改完若忘记重建 ``static/``，这里会失败
    —— 这正是本项的历史代价（前端产物随仓库分发）。
    """
    static_dir = pathlib.Path(server.__file__).parent / "static"
    assets_dir = static_dir / "assets"
    if not assets_dir.exists():
        pytest.skip("前端尚未构建，缺少 static/assets")

    chunks = []
    for chunk in assets_dir.glob("*.js"):
        text = chunk.read_text(encoding="utf-8")
        # `llm-form` 是 LlmConfig.vue 的 scoped class，用它定位该组件所在的 chunk。
        if "llm-form" in text:
            chunks.append((chunk.name, text))
    assert chunks, "未找到打包后的 LLM 配置组件"

    missing = [name for name, text in chunks if "留空表示不修改" not in text]
    assert not missing, f"以下产物的 LLM 配置界面未体现「留空表示不修改」: {missing}"
