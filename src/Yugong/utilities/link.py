import re

from src.Yugong.core.logger import utilities_logger


def make_anchor_link(title: str, link: str) -> str:
    """
    Format a topic name as [[PageName#TopicName|TopicName]].

    Args:
        title: Page title
        link: Topic name

    Returns:
        str: Formatted link
    """
    link_clean = clean_inner_link(link)
    display = link_clean.replace('Template link: ', '')
    return f"[[{title}#{link_clean}|{display}]]"


def clean_inner_link(text: str) -> str:
    text = re.sub(r'<span\b[^>]*>.*?</span>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[\[:?(.*?)\]\]', r'\1', text)
    text = re.sub(r'tl\|(.+)', r'Template link: {{\1}}', text)
    text = text.translate(_TARGET_ESCAPE_TABLE)

    return text

_TARGET_ESCAPE_TABLE = str.maketrans({
    '#': '&#35;', '<': '&#60;', '>': '&#62;',
    '[': '&#91;', ']': '&#93;', '|': '&#124;',
    '{': '&#123;', '}': '&#125;'
})

def get_user_talk(user: str, pure: bool = False) -> str:
    """
    Get the user talk page name.

    Args:
        user: Username

    Returns:
        str: User talk page name
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
        utilities_logger.critical("Username parsing error: invalid username")
        return ""

    # Capitalize first letter of username
    username = user[5:]
    if username:
        username = username[0].upper() + username[1:]

    if pure:
        return username
    return "User talk:" + username

def get_username(user: str, pure: bool = False) -> str:
    """
    Get the username.

    Args:
        user: Username
        pure: If True, return only the name without the "User:" prefix

    Returns:
        str: Username
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
        utilities_logger.critical("Username parsing error: invalid username")
        return ""

    # Capitalize first letter of username
    username = user[5:]
    if username:
        username = username[0].upper() + username[1:]

    if pure:
        return username
    return "User:" + username