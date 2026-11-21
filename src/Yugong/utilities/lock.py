"""A PID-based lock file so two YuGong runs cannot edit the wiki at once.

The lock records the owning process id, so a lock left behind by a crashed run
is detected and reclaimed instead of blocking the next run forever.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.Yugong.utilities.path_helper import PROJECT_ROOT

LOCK_PATH: Path = PROJECT_ROOT / "data" / "lock"


def _pid_alive_windows(pid: int) -> bool:
    """Windows: ``os.kill(pid, 0)`` TERMINATES the process, so use OpenProcess."""
    import ctypes

    kernel32 = getattr(ctypes, "windll").kernel32
    process_query_limited_information = 0x1000
    still_active = 259
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            return _pid_alive_windows(pid)
        except OSError:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Alive, but owned by somebody else.
        return True
    except OSError:
        return False
    return True


def read_lock_pid() -> int | None:
    """Return the pid stored in the lock file, or ``None`` if unreadable."""
    try:
        return int(LOCK_PATH.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def lock() -> bool:
    """Try to acquire the run lock.

    Returns:
        ``True`` if this process now holds the lock, ``False`` if another live
        process holds it.
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    if LOCK_PATH.exists():
        holder = read_lock_pid()
        if holder is not None and holder != os.getpid() and _pid_alive(holder):
            return False
        # Stale lock from a crashed or finished run.
        LOCK_PATH.unlink(missing_ok=True)

    try:
        with LOCK_PATH.open("x", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        return False


def unlock() -> None:
    """Release the lock if this process still owns it."""
    # Do not delete another process's lock if ours was reclaimed as stale.
    if read_lock_pid() != os.getpid():
        return
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass
