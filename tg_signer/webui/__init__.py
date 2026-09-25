"""WebUI 子模块。

前后端分离架构：
- 后端 ``tg_signer.webui.server`` 提供 FastAPI REST API 并托管 Vue 前端
  构建产物（``tg_signer/webui/static``）。
- 前端源码位于仓库 ``webui_frontend/``（Vue 3 + Vite），构建产物随包发布。

轻量子模块 ``data`` / ``runner`` / ``account`` / ``auth`` / ``schema_utils``
在导入时不依赖 FastAPI，因此在没有安装 ``tg-signer[gui]`` 额外依赖的环境
（例如 CI 默认 Linux runner、纯 CLI 部署）里，``from tg_signer.webui import
data`` 之类的语句仍然可以正常解析。

依赖 FastAPI 的入口（``AUTH_CODE_ENV`` / ``app`` / ``main`` /
``require_auth``）位于 ``tg_signer.webui.server`` 模块中，本模块通过
PEP 562 模块级 ``__getattr__`` 按需懒加载它们，既保持
``from tg_signer.webui import main`` 的向后兼容，又避免仅做单测或纯 CLI
调用时强依赖 FastAPI。
"""

from tg_signer.webui import account, auth, data, runner, schema_utils

__all__ = [
    "account",
    "auth",
    "data",
    "runner",
    "schema_utils",
    "AUTH_CODE_ENV",
    "app",
    "main",
    "require_auth",
]


_LAZY_SERVER_ATTRS = {"AUTH_CODE_ENV", "app", "main", "require_auth"}


def __getattr__(name):
    """按需从 ``tg_signer.webui.server`` 加载 FastAPI 相关符号。"""
    if name in _LAZY_SERVER_ATTRS:
        from tg_signer.webui import server as _server

        value = getattr(_server, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'tg_signer.webui' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals().keys()) | set(__all__))
