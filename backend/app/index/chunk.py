def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + size])
        if i + size >= len(text):
            break
        i += step
    return chunks


def chunk_starts(text: str, size: int = 800, overlap: int = 100) -> list[int]:
    """与 chunk_text 使用相同边界逻辑，返回各 chunk 在 strip 后正文中的起始偏移。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [0]
    step = max(1, size - overlap)
    starts: list[int] = []
    i = 0
    while i < len(text):
        starts.append(i)
        if i + size >= len(text):
            break
        i += step
    return starts
