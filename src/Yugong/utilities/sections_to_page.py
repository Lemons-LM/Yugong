def sections_to_page(sections: list, *, original_content: str=""):
    """
    Combine multiple sections into a page string.
    """
    result = original_content.strip()

    if result and not result.endswith("\n"):
        result += "\n"

    for section in sections:
        section_code = str(section).strip()
        result += section_code + "\n\n"

    return result
