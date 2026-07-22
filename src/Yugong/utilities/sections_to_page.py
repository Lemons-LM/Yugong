def sections_to_page(sections: list, *, original_content: str=""):
    """
    将多个段落转为页面
    """
    result = original_content.strip()

    if result and not result.endswith("\n"):
        result += "\n"

    for section in sections:
        section_code = str(section).strip()
        result += section_code + "\n\n"

    return result
