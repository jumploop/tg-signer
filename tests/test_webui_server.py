"""FastAPI 后端 API 冒烟测试（Vue 前后端分离改造后的服务层）。

基于 ``fastapi.testclient.TestClient`` 验证后端 REST API 的核心路径：
状态/工作目录、配置 CRUD、签到记录、用户信息、LLM 配置、账号列表、
群组缓存、运行管理、日志与鉴权。需要真实网络的端点（实时拉取对话、
发送验证码、LLM 连通性测试）不在此处执行。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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
def client(tmp_path):
    """每个测试使用独立工作目录，并在临时目录中启动应用。"""
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


def test_config_template(client):
    signer_tpl = client.get("/api/configs/signer/template")
    assert signer_tpl.status_code == 200
    assert "chats" in signer_tpl.json()["payload"]

    monitor_tpl = client.get("/api/configs/monitor/template")
    assert monitor_tpl.status_code == 200
    assert "match_cfgs" in monitor_tpl.json()["payload"]

    assert client.get("/api/configs/unknown/template").status_code == 400


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


def test_llm_config_roundtrip(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = client.post(
        "/api/llm-config",
        json={
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 200

    payload = client.get("/api/llm-config").json()
    assert payload["has_env"] is False
    assert payload["config"]["api_key"] == "sk-test"
    assert payload["config"]["base_url"] == "https://example.com/v1"
    assert payload["config"]["model"] == "gpt-4o-mini"


def test_llm_config_rejects_empty_key(client):
    resp = client.post("/api/llm-config", json={"api_key": "   "})
    assert resp.status_code == 400


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
    assert client.get("/api/run").json() == {"tasks": {}}

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


def test_index_served_or_reports_missing_build(client):
    resp = client.get("/")
    assert resp.status_code in (200, 503)
