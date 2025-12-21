JOBS = []
INTROS = []

def job(func: callable) -> callable:
    JOBS.append(func)
    return func

def intro(func: callable) -> callable:
    INTROS.append(func)
    return func