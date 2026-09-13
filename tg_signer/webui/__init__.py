"""WebUI 子模块。

轻量子模块 ``data`` / ``runner`` / ``account`` / ``auth`` / ``schema_utils``
在导入时不依赖 NiceGUI,因此在没有安装 ``tg-signer[gui]`` 额外依赖的环境
(例如 CI 默认 Linux runner、纯 CLI 部署)里,``from tg_signer.webui import
data`` 之类的语句仍然可以正常解析。

依赖 NiceGUI 的入口(``AUTH_CODE_ENV`` / ``build_ui`` / ``main``)位于
``tg_signer.webui.app`` 模块中,本模块通过 PEP 562 模块级 ``__getattr__``
按需懒加载它们,既保持 ``from tg_signer.webui import main`` 的向后兼容,
又避免仅做单测或纯 CLI 调用时强依赖 NiceGUI。
"""

from tg_signer.webui import account, auth, data, runner, schema_utils

__all__ = [
    "account",
    "auth",
    "data",
    "runner",
    "schema_utils",
    "AUTH_CODE_ENV",
    "build_ui",
    "main",
]


_LAZY_APP_ATTRS = {"AUTH_CODE_ENV", "build_ui", "main"}


def __getattr__(name):
    """按需从 ``tg_signer.webui.app`` 加载 NiceGUI 相关符号。"""
    if name in _LAZY_APP_ATTRS:
        from tg_signer.webui import app as _app

        value = getattr(_app, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'tg_signer.webui' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals().keys()) | set(__all__))
