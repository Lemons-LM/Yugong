from datetime import datetime, timezone, timedelta

# Module-level variable, initially None; set to current UTC+8 time by record_start_time()
START_TIME = None

def record_start_time() -> None:
    """Record the current UTC+8 (CST) time to the global START_TIME variable."""
    global START_TIME
    # UTC+8 timezone
    tz = timezone(timedelta(hours=8))
    START_TIME = datetime.now(tz)