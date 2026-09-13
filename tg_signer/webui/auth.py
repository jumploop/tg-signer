"""Reusable auth helpers for the WebUI (kept free of NiceGUI imports so they can be unit tested)."""

import time
from typing import Any, Dict, Optional

AUTH_MAX_ATTEMPTS = 5
AUTH_LOCKOUT_SECONDS = 60
AUTH_ATTEMPTS_KEY = "auth_failed_attempts"
AUTH_LOCK_UNTIL_KEY = "auth_locked_until"


def auth_lock_remaining(storage: Dict[str, Any]) -> float:
    """Return the number of seconds remaining in the current lockout (0 means unlocked)."""
    locked_until = storage.get(AUTH_LOCK_UNTIL_KEY, 0.0)
    try:
        locked_until = float(locked_until)
    except (TypeError, ValueError):
        locked_until = 0.0
    return max(0.0, locked_until - time.monotonic())


def is_auth_locked(storage: Dict[str, Any]) -> bool:
    return auth_lock_remaining(storage) > 0


def record_auth_failure(storage: Dict[str, Any]) -> Optional[float]:
    """Record one failed attempt; on reaching the cap, lock for AUTH_LOCKOUT_SECONDS."""
    attempts = storage.get(AUTH_ATTEMPTS_KEY, 0)
    try:
        attempts = int(attempts)
    except (TypeError, ValueError):
        attempts = 0
    attempts += 1
    storage[AUTH_ATTEMPTS_KEY] = attempts
    if attempts >= AUTH_MAX_ATTEMPTS:
        storage[AUTH_LOCK_UNTIL_KEY] = time.monotonic() + AUTH_LOCKOUT_SECONDS
        storage[AUTH_ATTEMPTS_KEY] = 0
        return AUTH_LOCKOUT_SECONDS
    return None


def clear_auth_failures(storage: Dict[str, Any]) -> None:
    storage.pop(AUTH_ATTEMPTS_KEY, None)
    storage.pop(AUTH_LOCK_UNTIL_KEY, None)
