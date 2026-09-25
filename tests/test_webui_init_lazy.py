"""Verify that ``tg_signer.webui`` does not eagerly import FastAPI.

The WebUI backend is an *optional* extra (``pip install tg-signer[gui]``
provides ``fastapi`` / ``uvicorn``). The core CLI plus most tests must
remain runnable on environments that never install the GUI extra (CI
runners without it, slim Docker images, etc.). The package's ``__init__``
therefore uses a PEP 562 module-level ``__getattr__`` to lazily load the
FastAPI-bound entry points (``AUTH_CODE_ENV``, ``app``, ``main``,
``require_auth``) only when they are actually accessed.

These tests exercise that contract by mutating ``sys.modules`` to pretend
FastAPI is not installed, then asserting that:

* ``import tg_signer.webui`` does **not** load ``tg_signer.webui.server``.
* ``from tg_signer.webui import data`` / ``runner`` / ``account`` /
  ``auth`` succeeds without FastAPI.
* Accessing ``AUTH_CODE_ENV`` / ``app`` / ``main`` / ``require_auth``
  triggers a ``ModuleNotFoundError`` (lazy load attempts to pull in
  FastAPI).
"""

from __future__ import annotations

import importlib
import sys

import pytest

_LAZY_ATTRS = ("AUTH_CODE_ENV", "app", "main", "require_auth")
_EAGER_SUBMODULES = ("data", "runner", "account", "auth")


def _block_fastapi():
    """Hide ``fastapi`` from import machinery for the duration of a block.

    Returns a callable that restores the original state. Sets
    ``sys.modules['fastapi'] = None`` so any ``import fastapi`` raises
    ``ModuleNotFoundError`` immediately.
    """
    saved = sys.modules.pop("fastapi", None)
    sys.modules["fastapi"] = None
    return saved


def _restore_fastapi(saved):
    if saved is None:
        sys.modules.pop("fastapi", None)
    else:
        sys.modules["fastapi"] = saved


@pytest.fixture
def fastapi_blocked():
    """Run the test body with ``fastapi`` hidden from imports."""
    saved = _block_fastapi()
    # Drop any cached webui modules so the package re-imports cleanly
    # under the simulated environment.
    for name in [
        m
        for m in list(sys.modules)
        if m == "tg_signer.webui" or m.startswith("tg_signer.webui.")
    ]:
        del sys.modules[name]
    try:
        yield
    finally:
        for name in [
            m
            for m in list(sys.modules)
            if m == "tg_signer.webui" or m.startswith("tg_signer.webui.")
        ]:
            del sys.modules[name]
        _restore_fastapi(saved)


def test_webui_package_does_not_load_server_without_fastapi(fastapi_blocked):
    """Importing the package must not pull in ``tg_signer.webui.server``."""
    import tg_signer.webui  # noqa: F401  (must succeed)

    assert "tg_signer.webui.server" not in sys.modules, (
        "tg_signer.webui.__init__ eagerly imported server.py; "
        "the optional WebUI dependency (fastapi) should not be required."
    )


def test_eager_submodules_load_without_fastapi(fastapi_blocked):
    """The light-weight WebUI submodules are safe to import on their own."""
    from tg_signer.webui import data, runner

    assert data.LOG_FILE_NAME == "tg-signer.log"
    assert runner.DEFAULT_LOG_FILE_NAME == "tg-signer.log"
    # All declared eager submodules should be importable from the package.
    webui_pkg = sys.modules["tg_signer.webui"]
    for mod_name in _EAGER_SUBMODULES:
        assert getattr(webui_pkg, mod_name) is not None


def test_lazy_attrs_fail_when_fastapi_missing(fastapi_blocked):
    """Accessing a lazy attr should raise ``ModuleNotFoundError`` (or
    ``ImportError``) because FastAPI cannot be imported."""
    import tg_signer.webui

    for attr in _LAZY_ATTRS:
        with pytest.raises((ModuleNotFoundError, ImportError)):
            getattr(tg_signer.webui, attr)


def test_webui_getattr_rejects_unknown_attribute():
    """Unknown attribute names raise a clean ``AttributeError``."""
    import tg_signer.webui

    with pytest.raises(AttributeError):
        _ = tg_signer.webui.totally_made_up_name


def test_webui_all_lists_eager_and_lazy_symbols():
    """``__all__`` advertises both eager submodules and lazy attrs."""
    import tg_signer.webui

    expected = set(_EAGER_SUBMODULES) | set(_LAZY_ATTRS)
    assert expected.issubset(set(tg_signer.webui.__all__))


def test_lazy_attr_works_when_fastapi_present():
    """When FastAPI is actually importable, lazy attrs resolve correctly
    and are cached on the module after first access.

    Only runs in environments that have the optional ``[gui]`` extra
    installed; on slim CI images / default installs the test is skipped
    (the no-fastapi paths are already covered by the prior tests).
    """
    pytest.importorskip("fastapi")

    import tg_signer.webui

    # Ensure fresh import state for the assertion below.
    importlib.reload(tg_signer.webui)

    # AUTH_CODE_ENV should be loadable end-to-end.
    auth_env = tg_signer.webui.AUTH_CODE_ENV
    assert isinstance(auth_env, str)

    # After resolution, the value should be cached on the module.
    assert tg_signer.webui.AUTH_CODE_ENV is auth_env
