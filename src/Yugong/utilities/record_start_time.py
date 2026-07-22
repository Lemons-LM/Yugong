from datetime import datetime, timezone, timedelta

# 顶级变量，初始为 None，调用 record_start_time() 后赋值为东八区当前时间
START_TIME = None

def record_start_time() -> None:
    """记录当前东八区时间到全局变量 START_TIME"""
    global START_TIME
    # 定义东八区时区（UTC+8）
    tz = timezone(timedelta(hours=8))
    START_TIME = datetime.now(tz)