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
import secrets
import threading
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tg_signer.ai_tools import OpenAIConfigManager, test_openai_connection
from tg_signer.webui import account as account_mod
from tg_signer.webui import auth as auth_helpers
from tg_signer.webui import data as data_mod
from tg_signer.webui import runner as runner_mod

AUTH_CODE_ENV = "TG_SIGNER_GUI_AUTHCODE"

# 视为「仅本机可访问」的监听地址；其余地址必须配合授权码启动。
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

_auth_storage: Dict[str, Any] = {}
# 失败计数是「读-改-写」,同步依赖由 FastAPI 放进线程池执行;不加锁时并发请求
# 会各自读到同一份旧值再写回,把「连续 5 次错误锁定 60 秒」直接绕过。
_auth_storage_lock = threading.Lock()

# create=False：模块级 state 在 import 时构造，而 UIState 过去会 mkdir 工作目录，
# 于是「仅仅 import 一下」就会在进程 CWD 下凭空建出 `.signer` —— 传了
# --workdir 也照样建，随后 main() 改回真正的 workdir，那个野目录却留在磁盘上。
# 目录改由 _setup_logger()（经 _setup_webui_logger 的 mkdir）在启动时创建。
state = data_mod.UIState(create=False)

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
    # 「先验后锁」：凭据正确直接放行，不受锁定期影响；错误才记账并触发限流。
    # 旧实现是「先锁后验」，结果锁定期内正确授权码同样被 429 —— 锁定因此成了
    # 未认证者可用的 DoS 原语（5 次错误请求即可把合法用户锁在门外整整一分钟）。
    # 同时记账必须发生在【任何】携带错误凭据的请求上：它原来只挂在 /api/auth/login，
    # 攻击者改打任意受保护端点携带猜测的 Bearer 就能完全绕开限流。
    with _auth_storage_lock:
        provided = (authorization or "").encode("utf-8")
        wanted = f"Bearer {expected}".encode("utf-8")
        if secrets.compare_digest(provided, wanted):
            return
        auth_helpers.record_auth_failure(_auth_storage)
        if auth_helpers.is_auth_locked(_auth_storage):
            remaining = auth_helpers.auth_lock_remaining(_auth_storage)
            raise HTTPException(
                status_code=429,
                detail=f"尝试次数过多，请 {remaining:.0f} 秒后再试",
            )
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
    previous = state.workdir
    previous_log = state.log_path
    try:
        state.set_workdir(body.workdir)
        # 日志 handler 是进程启动时按当时的 workdir 绑定的，不重绑的话
        # /api/state 显示的 log_path 已经是新目录，实际日志却仍写进旧目录 ——
        # 基础设置页显示的「主日志路径」就成了假路径，而新目录的 logs/ 根本
        # 不会被创建（切到一个全新目录时日志页直接空白）。
        data_mod._setup_webui_logger(state.workdir)
    except Exception as exc:  # noqa: BLE001
        # set_workdir() 成功之后本函数已无回滚点：若这里直接抛 400，后端其实
        # 已经切到新目录在操作，而前端收到失败后保留旧值显示 —— 正是「基础设置
        # 显示的路径和实际不一致」。必须把状态和日志 handler 一起退回去。
        state.workdir = previous
        state.log_path = previous_log
        try:
            data_mod._setup_webui_logger(state.workdir)
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=400, detail=f"切换工作目录失败: {exc}")
    return {"workdir": str(state.workdir), "log_path": str(state.log_path)}


# ---------------------------------------------------------------------------
# 配置管理（signer / automation）
# ---------------------------------------------------------------------------


@app.get("/api/configs/{kind}")
def list_configs(kind: str, _: None = Depends(require_auth)) -> Dict[str, List[str]]:
    if kind == "automation":
        # 只提供任务名列表供「任务运行」页选择;automation 配置编辑仍走 CLI。
        return {"names": data_mod.list_automation_names(state.workdir)}
    if not data_mod.uses_dir_layout(kind):
        raise HTTPException(status_code=400, detail=f"不支持的配置类型: {kind}")
    return {"names": data_mod.list_task_names(kind, state.workdir)}


@app.get("/api/configs/{kind}/template")
def config_template(kind: str, _: None = Depends(require_auth)) -> Dict[str, Any]:
    if kind == "signer":
        return {"payload": copy.deepcopy(SIGNER_TEMPLATE)}
    if kind == "automation":
        return {"payload": copy.deepcopy(AUTOMATION_TEMPLATE)}
    raise HTTPException(status_code=400, detail=f"不支持的配置类型: {kind}")


@app.get("/api/configs/{kind}/suggest-name")
def config_suggest_name(
    kind: str,
    chat_id: str = Query(default=""),
    title: str = Query(default=""),
    username: str = Query(default=""),
    _: None = Depends(require_auth),
) -> Dict[str, str]:
    """为「群组/频道 → 复制到配置」生成一个未被占用的默认配置名。"""
    if kind not in data_mod.CONFIG_KINDS:
        raise HTTPException(status_code=400, detail=f"不支持的配置类型: {kind}")
    chat = {"id": chat_id, "title": title, "username": username}
    return {"name": data_mod.generate_random_config_name(kind, chat, state.workdir)}


@app.get("/api/configs/{kind}/{name}")
def get_config(kind: str, name: str, _: None = Depends(require_auth)) -> Dict[str, Any]:
    try:
        if kind == "automation":
            entry = data_mod.load_automation_config(name, workdir=state.workdir)
        else:
            if not data_mod.uses_dir_layout(kind):
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
            if not data_mod.uses_dir_layout(kind):
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
            if not data_mod.uses_dir_layout(kind):
                raise HTTPException(status_code=400, detail=f"不支持的配置类型: {kind}")
            data_mod.delete_config(kind, name, workdir=state.workdir)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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


def _mask_api_key(api_key: str) -> str:
    """把密钥渲染成仅供展示的掩码,明文不出服务端。"""
    key = (api_key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"****{key[-4:]}"


def _llm_manager() -> OpenAIConfigManager:
    return OpenAIConfigManager(state.workdir)


@app.get("/api/llm-config")
def get_llm_config(_: None = Depends(require_auth)) -> Dict[str, Any]:
    manager = _llm_manager()
    has_env = manager.has_env_config()
    cfg = manager.load_config() or {}
    return {
        "has_env": has_env,
        "config": {
            "api_key": _mask_api_key(cfg.get("api_key", "")),
            "base_url": cfg.get("base_url") or "",
            "model": cfg.get("model") or "",
        },
    }


@app.post("/api/llm-config")
def save_llm_config(
    body: LmConfigBody, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    """保存 LLM 配置。

    ``api_key`` 为空、或恰好是服务端回显的掩码时都视为「不修改已有密钥」,
    这样前端即使把回显值原样提交回来也不会覆盖真实密钥。
    """
    manager = _llm_manager()
    stored_key = (manager.load_file_config() or {}).get("api_key", "").strip()
    effective_key = (manager.load_config() or {}).get("api_key", "").strip()

    posted = (body.api_key or "").strip()
    if posted and posted not in (
        _mask_api_key(stored_key),
        _mask_api_key(effective_key),
    ):
        api_key = posted
    elif stored_key:
        api_key = stored_key
    else:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    manager.save_config(
        api_key,
        base_url=(body.base_url or "").strip() or None,
        model=(body.model or "").strip() or None,
    )
    return {"ok": True, "api_key_unchanged": api_key != posted}


@app.post("/api/llm-config/test")
async def test_llm_config(
    body: LmConfigBody, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    manager = _llm_manager()
    api_key = (body.api_key or "").strip()
    if not api_key or api_key == _mask_api_key(
        (manager.load_config() or {}).get("api_key", "")
    ):
        # 前端回显的是掩码(或留空)时,用服务端已保存的密钥去测连通性。
        api_key = (manager.load_config() or {}).get("api_key", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    ok, message = await test_openai_connection(
        api_key,
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
    try:
        result, message = await asyncio.to_thread(
            account_mod.send_login_code, body.account, body.phone, state.workdir
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
    try:
        ok, message = await account_mod.is_account_authorized(account, state.workdir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": ok, "message": message}


@app.post("/api/accounts/logout")
async def account_logout(
    body: AccountBody, _: None = Depends(require_auth)
) -> Dict[str, Any]:
    try:
        message = await account_mod.logout_account(body.account, state.workdir)
    except (RuntimeError, ValueError) as exc:
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
    try:
        ok, message, chats = await account_mod.fetch_dialogs(
            body.account, state.workdir, 50
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
    try:
        resolved, lines = data_mod.load_logs(
            limit=limit,
            # 传 None 而不是 str(state.log_path)：让 _resolve_log_path 回退到
            # 「非空 + 最新」的那个文件，而不是常常是 0 字节的主日志。
            log_path=path,
            # 只允许读 <workdir>/logs 下的文件,挡住任意文件读取。
            log_dir=state.log_path.parent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"path": str(resolved), "lines": lines}


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------


@app.get("/api/auth/status")
def auth_status() -> Dict[str, Any]:
    with _auth_storage_lock:
        locked_remaining = auth_helpers.auth_lock_remaining(_auth_storage)
    return {
        "required": bool(_expected_auth_code()),
        "locked_until": locked_remaining,
    }


@app.post("/api/auth/login")
def auth_login(body: AuthBody) -> Dict[str, Any]:
    expected = _expected_auth_code()
    if not expected:
        return {"ok": True, "message": "未启用授权码"}
    # 判断与记录必须在同一把锁里,否则「第 5 次失败」会被并发请求拆成多次
    # 「还差几次」,锁定永远触发不了。
    with _auth_storage_lock:
        # 「先比后锁」：正确授权码即使在锁定期内也放行（并清空计数），
        # 否则未认证者可以用 5 次错误请求把合法用户锁在门外。
        if secrets.compare_digest(body.code.encode("utf-8"), expected.encode("utf-8")):
            auth_helpers.clear_auth_failures(_auth_storage)
            return {"ok": True, "message": "登录成功"}
        auth_helpers.record_auth_failure(_auth_storage)
        if auth_helpers.is_auth_locked(_auth_storage):
            remaining = auth_helpers.auth_lock_remaining(_auth_storage)
            raise HTTPException(
                status_code=429, detail=f"尝试次数过多，请 {remaining:.0f} 秒后再试"
            )
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
    # index.html 引用的是带内容 hash 的 chunk 文件名。升级后 chunk 会被重命名
    # （例如 Configs-D3OhaQpj.js -> Configs-DeKRQTYv.js）。若浏览器缓存了旧版
    # index.html，就会去请求已不存在的旧 chunk 并收到 404，表现为整页白屏。
    # 这里显式要求每次回源校验；配合下方 assets 的 immutable 缓存。
    return FileResponse(
        index_file,
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


class ImmutableStaticFiles(StaticFiles):
    # 给带内容 hash 的构建产物加长期缓存。文件名中的 hash 随内容变化，
    # 内容变了文件名必然变，因此可以安全地 immutable 缓存，同时避免每次
    # 升级后重新下载全部 chunk。

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


if STATIC_DIR.is_dir() and (STATIC_DIR / "assets").is_dir():
    app.mount(
        "/assets",
        ImmutableStaticFiles(directory=STATIC_DIR / "assets"),
        name="assets",
    )


def main(
    host: str = None,
    port: int = None,
    workdir: str = None,
) -> None:
    """启动后端服务：``tg-signer webgui`` 入口。"""
    import uvicorn

    host = host or "127.0.0.1"
    port = int(port or 8080)
    # 之前 webgui 子命令完全不理会全局 --workdir，WebUI 永远读 CWD 下的
    # ``.signer``：CLI 明明指定了工作目录，日志却在别处，页面自然什么都没有。
    if workdir:
        state.init_workdir(str(workdir))
    if host not in LOOPBACK_HOSTS and not _expected_auth_code():
        # fail-closed：监听非回环地址意味着整个网络都能访问这些接口
        # （账号登录/注销、读日志、拉起任务），没有授权码等同于无鉴权开放。
        raise SystemExit(
            f"拒绝启动：监听 {host} 会让 WebUI 对整个网络开放，"
            f"请通过 --auth-code 或环境变量 {AUTH_CODE_ENV} 设置授权码。"
        )
    _setup_logger()
    uvicorn.run(app, host=host, port=port, log_level="info")


__all__ = ["AUTH_CODE_ENV", "app", "main", "require_auth"]
