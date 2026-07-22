from src.Yugong.utilities.path_helper import PROJECT_ROOT


def lock() -> bool:
    """
    尝试获取锁（创建锁文件）。
    如果锁文件不存在，则创建并返回 True；
    如果已存在，则返回 False（表示有其他进程持有锁）。
    """
    lock_path = PROJECT_ROOT / "data" / "lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)  # 确保 data 目录存在

    try:
        with lock_path.open('xb'):
            pass
        return True
    except FileExistsError:
        return False

def unlock() -> None:
    """释放锁（删除锁文件）。若文件不存在则静默忽略。"""
    lock_path = PROJECT_ROOT / "data" / "lock"
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass