def section_title(content: str) -> str:
    """The Markdown heading a chunk starts with ('## Transfer times' -> 'Transfer times'), or ''."""
    first = content.lstrip().split("\n", 1)[0]
    return first.lstrip("#").strip() if first.startswith("#") else ""
