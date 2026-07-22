import re

from src.Yugong.core.logger import utilities_logger


def make_anchor_link(title: str, link: str) -> str:
    """
    将话题名称格式化为 [[页面名称#话题名称|话题名称]] 形式

    Args:
        title: 页面标题
        link: 话题名称

    Returns:
        str: 格式化后的链接
    """
    link_clean = clean_inner_link(link)
    display = link_clean.replace('模板链接：', '')
    return f"[[{title}#{link_clean}|{display}]]"


def clean_inner_link(text: str) -> str:
    text = re.sub(r'<span\b[^>]*>.*?</span>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[\[:?(.*?)\]\]', r'\1', text)
    text = re.sub(r'tl\|(.+)', r'模板链接：{{\1}}', text)
    text = text.translate(_TARGET_ESCAPE_TABLE)

    return text

_TARGET_ESCAPE_TABLE = str.maketrans({
    '#': '&#35;', '<': '&#60;', '>': '&#62;',
    '[': '&#91;', ']': '&#93;', '|': '&#124;',
    '{': '&#123;', '}': '&#125;'
})

def get_user_talk(user: str, pure: bool = False) -> str:
    """
    获取用户讨论页面名称

    Args:
        user: 用户名

    Returns:
        str: 用户讨论页面名称
    """
    match = re.match(r"^\[\[(.*)\]\]$", user)
    if match:
        user = match.group(1)

    user = user.split("|")[0]
    user = user.split("/")[0]
    user = user.split("#")[0]
    user = user.replace("_", " ")

    if user.lower().startswith("user:"):
        user = "User:" + user[5:]
    elif user.startswith("User talk:"):
        user = "User:" + user[10:]
    elif ":" not in user:
        user = "User:" + user
    else:
        utilities_logger.critical("用户名分割出错！非法的用户名")
        return ""

    # 用户名首字母大写
    username = user[5:]
    if username:
        username = username[0].upper() + username[1:]

    if pure:
        return username
    return "User talk:" + username

def get_username(user: str, pure: bool = False) -> str:
    """
    获取用户名

    Args:
        user: 用户名
        pure: 是否仅返回用户名（不含 User: 前缀）

    Returns:
        str: 用户名
    """
    match = re.match(r"^\[\[(.*)\]\]$", user)
    if match:
        user = match.group(1)

    user = user.split("|")[0]
    user = user.split("/")[0]
    user = user.split("#")[0]
    user = user.replace("_", " ")

    if user.lower().startswith("user:"):
        user = "User:" + user[5:]
    elif user.startswith("User talk:"):
        user = "User:" + user[10:]
    elif ":" not in user:
        user = "User:" + user
    else:
        utilities_logger.critical("用户名分割出错！非法的用户名")
        return ""

    # 用户名首字母大写
    username = user[5:]
    if username:
        username = username[0].upper() + username[1:]

    if pure:
        return username
    return "User:" + username