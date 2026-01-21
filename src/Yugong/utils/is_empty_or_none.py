def is_str_empty_or_none(x: str):
    return x is None or x == ""

def is_list_empty_or_none(x: list):
    return x is None or len(x) == 0

def is_int_lt_or_none(*, x: int, target: int) -> bool:
    return x is None or x < target
