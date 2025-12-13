def is_str_empty_or_none(x: str):
    return x == "" or x is None

def is_list_empty_or_none(x: list):
    return len(x) == 0 or x is None

def is_int_lt_or_none(*, x: int, target: int) -> bool:
    return x < target or x is None