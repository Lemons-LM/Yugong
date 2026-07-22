from src.Yugong.utilities.path_helper import PROJECT_ROOT


def lock() -> bool:
    """
    Try to acquire a lock (create a lock file).
    Returns True if lock was acquired, False if already held by another process.
    """
    lock_path = PROJECT_ROOT / "data" / "lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)  # ensure data dir exists

    try:
        with lock_path.open('xb'):
            pass
        return True
    except FileExistsError:
        return False

def unlock() -> None:
    """Release the lock (delete lock file). Silently ignores if file doesn't exist."""
    lock_path = PROJECT_ROOT / "data" / "lock"
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass