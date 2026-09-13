import importlib.util
from pathlib import Path

_AUTH_PATH = Path(__file__).resolve().parents[1] / "tg_signer" / "webui" / "auth.py"
_spec = importlib.util.spec_from_file_location("tg_signer_webui_auth", _AUTH_PATH)
auth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auth)


def test_auth_empty_storage_is_unlocked():
    storage = {}
    assert auth.auth_lock_remaining(storage) == 0.0
    assert auth.is_auth_locked(storage) is False


def test_auth_failure_increments_attempts():
    storage = {}
    assert auth.record_auth_failure(storage) is None
    assert storage[auth.AUTH_ATTEMPTS_KEY] == 1
    assert auth.is_auth_locked(storage) is False


def test_auth_max_attempts_locks():
    storage = {}
    for _ in range(auth.AUTH_MAX_ATTEMPTS - 1):
        assert auth.record_auth_failure(storage) is None
    locked_for = auth.record_auth_failure(storage)
    assert locked_for == auth.AUTH_LOCKOUT_SECONDS
    assert storage[auth.AUTH_ATTEMPTS_KEY] == 0
    assert auth.is_auth_locked(storage) is True
    assert auth.auth_lock_remaining(storage) > 0


def test_auth_clear_removes_state():
    storage = {}
    auth.record_auth_failure(storage)
    auth.clear_auth_failures(storage)
    assert storage == {}
