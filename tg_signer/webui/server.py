"""FastAPI 后端：为 Vue 前端提供 REST API 并托管静态产物。

复用 ``tg_signer.webui`` 下不依赖 UI 框架的逻辑模块（``data`` /
``account`` / ``runner`` / ``auth``），将原 NiceGUI 页面改造成
前后端分离架构。后端只提供 API 与静态文件服务，前端为
``tg_signer/webui/frontend/``（Vue 3 + Vite），构建产物位于
``tg_signer/webui/static``。
"""

from __future__ import annotations

import asyncio
import copy
import os
import pathlib
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tg_signer.ai_tools import OpenAIConfigManager, test_openai_connection
from tg_signer.webui import account as account_mod
from tg_signer.webui import auth as auth_helpers
from tg_signer.webui import data as data_mod
from tg_signer.webui import runner as runner_mod

AUTH_CODE_ENV = "TG_SIGNER_GUI_AUTHCODE"

_auth_storage: Dict[str, Any] = {}

state = data_mod.UIState()

SIGNER_TEMPLATE: Dict[str, object] = {
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

MONITOR_TEMPLATE: Dict[str, object] = {
    "match_cfgs": [
        {
            "chat_id": "@channel_or_user",
            "rule": "contains",
            "rule_value": "关键词",
            "from_user_ids": None,
            "always_ignore_me": False,
            "default_send_text": "自动回复",
            "ai_reply": False,
            "ai_prompt": None,
            "send_text_search_regex": None,
            "send_text_template": None,
            "delete_after": None,
            "ignore_case": True,
            "forward_to_chat_id": None,
            "external_forwards": None,
            "push_via_server_chan": False,
            "server_chan_send_key": None,
        }
    ]
}

AUTOMATION_TEMPLATE: Dict[str, object] = {
    "rules": [
        {
            "id": "demo_message_reply",
            "enabled": True,
            "triggers": [
                {
                    "id": None,
                    "type": "message",
                    "params": {
                        "chat_id": "@channel_or_user",
                        "chat_ids": None,
                        "from_user_ids": None,
                        "reply_to_me": False,
                        "reply_to_message_id": None,
                        "ignore_case": True,
                    },
                }
            ],
            "filters": {
                "chat_id": None,
                "chat_ids": None,
                "from_user_ids": None,
                "text_rule": "contains",
                "text_value": "关键词",
                "ignore_case": True,
            },
            "handlers": [{"handler": "send_text", "params": {"text": "自动回复"}}],
            "vars": {},
        }
    ]
}


def _expected_auth_code() -> Optional[str]:
    return os.environ.get(AUTH_CODE_ENV) or None


def _setup_logger() -> None:
    """把 WebUI 自身日志落到 <workdir>/logs/tg-signer.log。"""
    data_mod._setup_webui_logger(state.workdir)


class StateBody(BaseModel):
    workdir: str


class LmConfigBody(BaseModel):
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None


class AccountBody(BaseModel):
    account: str


class LoginCodeBody(BaseModel):
    account: str
    phone: str


class LoginCompleteBody(BaseModel):
    account: str
    code: str
    password: Optional[str] = None


class RunStartBody(BaseModel):
    kind: str
    tasks: List[str]
    account: str
    proxy: Optional[str] = None


class RunStopBody(BaseModel):
    kind: str
    account: str


class AuthBody(BaseModel):
    code: str


class ChatFetchBody(BaseModel):
    account: str


def _challenge() -> HTTPException:
    return HTTPException(status_code=401, detail="未授权或授权码错误")


def require_auth(
    authorization: Optional[str] = Header(default=None),
) -> None:
    expected = _expected_auth_code()
    if not expected:
        return
    if auth_helpers.is_auth_locked(_auth_storage):
        remaining = auth_helpers.auth_lock_remaining(_auth_storage)
        raise HTTPException(
            status_code=429,
            detail=f"尝试次数过多，请 {remaining:.0f} 秒后再试",
        )
    if authorization != f"Bearer {expected}":
        raise _challenge()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _setup_logger()
    yield
    # 关闭服务时终止受管子进程，避免遗留孤儿进程。
    stopped = runner_mod.shutdown_all()
    if stopped:
        print(f"WebUI 关闭，已停止任务进程: {stopped}")


app = FastAPI(title="tg-signer WebUI", lifespan=_lifespan)


def _config_entry_payload(entry: data_mod.ConfigEntry) -> Dict[str, Any]:
    return {
        "name": entry.name,
        "path": str(entry.path),
        "updated_from_old": entry.updated_from_old,
        "payload": entry.payload,
    }


def _sign_records_payload(
    records: List[data_mod.SignRecord],
) -> List[Dict[str, Any]]:
    return [
        {
            "task": record.task,
            "user_id": record.user_id,
            "path": str(record.path),
            "records": [
                {"sign_date": sign_date, "signed_at": signed_at}
                for sign_date, signed_at in record.records
            ],
        }
        for record in records
    ]


def _user_infos_payload(infos: List[data_mod.UserInfo]) -> List[Dict[str, Any]]:
    return [
        {
            "user_id": info.user_id,
            "path": str(info.path),
            "data": info.data,
            "latest_chats": info.latest_chats or [],
        }
        for info in infos
    ]


# ---------------------------------------------------------------------------
# 状态 / 基础设置
# ---------------------------------------------------------------------------


@app.get("/api/state")
def get_state(_: None = Depends(require_auth)) -> Dict[str, Any]:
    return {
        "workdir": str(state.workdir),
        "log_path": str(state.log_path),
        "auth_required": bool(_expected_auth_code()),
    }


@app.post("/api/state")
def set_state(body: StateBody, _: None = Depends(require_auth)) -> Dict[str, str]:
    try:
        state.set_workdir(body.workdir)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"切换工作目录失败: {exc}")
    return {"workdir": str(state.workdir), "log_path": str(state.log_path)}


# ---------------------------------------------------------------------------
# 配置管理（signer / monitor）
# ---------------------------------------------------------------------------


@app.get("/api/configs/{kind}")
def list_configs(kind: str, _: None = Depends(require_auth)) -> Dict[str, List[str]]:
    if kind == "automation":
        # 只提供任务名列表供「任务运行」页选择;automation 配置编辑仍走 CLI。
        return {"names": data_mod.list_automation_names(state.workdir)}
    if kind not in data_mod.CONFIG_META:
        raise HTTPException(status_code=400, detail=f"不支持的配置类型: {kind}")
    return {"names": data_mod.list_task_names(kind, state.workdir)}


@app.get("/api/configs/{kind}/template")
def config_template(kind: str, _: None = Depends(require_auth)) -> Dict[str, Any]:
    if kind == "signer":
        return {"payload": copy.deepcopy(SIGNER_TEMPLATE)}
    if kind == "monitor":
        return {"payload": copy.deepcopy(MONITOR_TEMPLATE)}
    if kind == "automation":
        return {"payload": copy.deepcopy(AUTOMATION_TEMPLATE)}
    raise HTTPException(status_code=400, detail=f"不支持的配置类型: {kind}")


@app.get("/api/configs/{kind}/{name}")
def get_config(kind: str, name: str, _: None = Depends(require_auth)) -> Dict[str, Any]:
    try:
        if kind == "automation":
            entry = data_mod.load_automation_config(name, workdir=state.workdir)
        else:
            if kind not in data_mod.CONFIG_META:
                raise HTTPException(status_code=400, detail=f"不支持的配置类型: {kind}")
            entry = data_mod.load_config(kind, name, workdir=state.workdir)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _config_entry_payload(entry)


@app.post("/api/configs/{kind}/{name}")
def save_config(
    kind: str,
    name: str,
    payload: Dict[str, Any],
    _: None = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        if kind == "automation":
            data_mod.save_automation_config(name, payload, workdir=state.workdir)
            entry = data_mod.load_automation_config(name, workdir=state.workdir)
        else:
            if kind not in data_mod.CONFIG_META:
                raise HTTPException(status_code=400, detail=f"不支持的配置类型: {kind}")
            data_mod.save_config(kind, name, payload, workdir=state.workdir)
            entry = data_mod.load_config(kind, name, workdir=state.workdir)
    except HTTPException:
        raise
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"配置校验失败: {exc}")
    return _config_entry_payload(entry)


@app.delete("/api/configs/{kind}/{name}")
def delete_config(
    kind: str, name: str, _: None = Depends(require_auth)
) -> Dict[str, bool]:
    try:
        if kind == "automation":
            data_mod.delete_automation_config(name, workdir=state.workdir)
        else:
            if kind not in data_mod.CONFIG_META:
                raise HTTPException(status_code=400, detail=f"不支持的配置类型: {kind}")
            data_mod.delete_config(kind, name, workdir=state.workdir)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


# ---------------------------------------------------------------------------
# 签到记录 / 用户信息
# ---------------------------------------------------------------------------


@app.get("/api/records")
def list_records(_: None = Depends(require_auth)) -> List[Dict[str, Any]]:
    return _sign_records_payload(data_mod.load_sign_records(state.workdir))


@app.get("/api/users")
def list_users(_: None = Depends(require_auth)) -> List[Dict[str, Any]]:
    return _user_infos_payload(data_mod.load_user_infos(state.workdir))


# ---------------------------------------------------------------------------
# 大模型配置
# ---------------------------------------------------------------------------


@app.get("/api/llm-config")
def get_llm_config(_: None = Depends(require_auth)) -> Dict[str, Any]:
    manager = OpenAIConfigManager(state.workdir)
    has_env = manager.has_env_config()
    cfg = manager.load_config()
    return {
        "has_env": has_env,
        "config": {
            "api_key": (cfg or {}).get("api_key", ""),
            "base_url": (cfg or {}).get("base_url") or "",
            "model": (cfg or {}).get("model") or "",
        },
    }


@app.post("/api/llm-config")
def save_llm_config(
    body: LmConfigBody, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    if not body.api_key.strip():
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    OpenAIConfigManager(state.workdir).save_config(
        body.api_key.strip(),
        base_url=(body.base_url or "").strip() or None,
        model=(body.model or "").strip() or None,
    )
    return {"ok": True}


@app.post("/api/llm-config/test")
async def test_llm_config(
    body: LmConfigBody, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    ok, message = await test_openai_connection(
        body.api_key,
        base_url=(body.base_url or "").strip() or None,
        model=(body.model or "").strip() or None,
    )
    return {"ok": ok, "message": message}


# ---------------------------------------------------------------------------
# 账号管理
# ---------------------------------------------------------------------------


@app.get("/api/accounts")
def list_accounts(_: None = Depends(require_auth)) -> List[Dict[str, Any]]:
    return account_mod.list_accounts(state.workdir)


@app.post("/api/accounts/send-code")
async def account_send_code(
    body: LoginCodeBody, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    result, message = await asyncio.to_thread(
        account_mod.send_login_code, body.account, body.phone, state.workdir
    )
    return {"result": result, "message": message}


@app.post("/api/accounts/complete-login")
async def account_complete_login(
    body: LoginCompleteBody, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    result, message = await asyncio.to_thread(
        account_mod.complete_login, body.account, body.code, body.password
    )
    return {"result": result, "message": message}


@app.get("/api/accounts/{account}/authorized")
async def account_authorized(
    account: str, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    ok, message = await account_mod.is_account_authorized(account, state.workdir)
    return {"ok": ok, "message": message}


@app.post("/api/accounts/logout")
async def account_logout(
    body: AccountBody, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    try:
        message = await account_mod.logout_account(body.account, state.workdir)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": message}


# ---------------------------------------------------------------------------
# 群组 / 频道
# ---------------------------------------------------------------------------


@app.get("/api/chats")
def list_chats(_: None = Depends(require_auth)) -> List[Dict[str, Any]]:
    return data_mod.load_group_chats(state.workdir)


@app.post("/api/chats/fetch")
async def fetch_chats(
    body: ChatFetchBody, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    ok, message, chats = await account_mod.fetch_dialogs(
        body.account, state.workdir, 50
    )
    return {"ok": ok, "message": message, "chats": chats}


# ---------------------------------------------------------------------------
# 运行管理
# ---------------------------------------------------------------------------


@app.get("/api/run")
def run_status(_: None = Depends(require_auth)) -> Dict[str, Any]:
    return {
        "tasks": runner_mod.running_tasks(),
        "task_names": runner_mod.running_task_names(),
    }


@app.post("/api/run/start")
def run_start(body: RunStartBody, _: None = Depends(require_auth)) -> Dict[str, Any]:
    ok, message = runner_mod.start(
        body.kind,
        body.tasks,
        state.workdir,
        body.account,
        proxy=body.proxy,
    )
    return {"ok": ok, "message": message}


@app.post("/api/run/stop")
def run_stop(body: RunStopBody, _: None = Depends(require_auth)) -> Dict[str, Any]:
    ok, message = runner_mod.stop(body.kind, body.account)
    return {"ok": ok, "message": message}


@app.post("/api/run/shutdown")
def run_shutdown(_: None = Depends(require_auth)) -> Dict[str, Any]:
    stopped = runner_mod.shutdown_all()
    return {"stopped": stopped}


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------


@app.get("/api/logs/files")
def list_logs(_: None = Depends(require_auth)) -> Dict[str, List[str]]:
    log_dir = state.log_path.parent
    return {"files": [str(p) for p in data_mod.list_log_files(log_dir)]}


@app.get("/api/logs")
def read_logs(
    path: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
    _: None = Depends(require_auth),
) -> Dict[str, Any]:
    resolved, lines = data_mod.load_logs(
        limit=limit,
        log_path=path if path is not None else str(state.log_path),
    )
    return {"path": str(resolved), "lines": lines}


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------


@app.get("/api/auth/status")
def auth_status() -> Dict[str, Any]:
    return {
        "required": bool(_expected_auth_code()),
        "locked_until": auth_helpers.auth_lock_remaining(_auth_storage),
    }


@app.post("/api/auth/login")
def auth_login(body: AuthBody) -> Dict[str, Any]:
    expected = _expected_auth_code()
    if not expected:
        return {"ok": True, "message": "未启用授权码"}
    if auth_helpers.is_auth_locked(_auth_storage):
        remaining = auth_helpers.auth_lock_remaining(_auth_storage)
        raise HTTPException(
            status_code=429, detail=f"尝试次数过多，请 {remaining:.0f} 秒后再试"
        )
    if body.code == expected:
        auth_helpers.clear_auth_failures(_auth_storage)
        return {"ok": True, "message": "登录成功"}
    auth_helpers.record_auth_failure(_auth_storage)
    return {"ok": False, "message": "授权码错误"}


# ---------------------------------------------------------------------------
# 静态资源
# ---------------------------------------------------------------------------

STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=503,
            detail="前端产物缺失，请先在 tg_signer/webui/frontend/ 执行 npm run build",
        )
    return FileResponse(index_file)


if STATIC_DIR.is_dir() and (STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


def main(
    host: str = None,
    port: int = None,
    storage_secret: str = None,  # noqa: ARG001 - NiceGUI 遗留参数，已不再需要
) -> None:
    """启动后端服务：``tg-signer webgui`` 入口。"""
    import uvicorn

    host = host or "127.0.0.1"
    port = int(port or 8080)
    _setup_logger()
    uvicorn.run(app, host=host, port=port, log_level="info")


__all__ = ["AUTH_CODE_ENV", "app", "main", "require_auth"]
