from __future__ import annotations

# KB 文档元数据定界（内部实现细节；工具对外只暴露结构化 meta）。
# 故意不用 Markdown 常见的 ---，以免与 Agent Skills 正文 YAML 冲突。
_OPEN = "<<<LORE_META"
_CLOSE = "LORE_META>>>"
_LEGACY_DELIM = "---"


def _parse_header_lines(header: str) -> dict:
    meta: dict = {}
    for line in header.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            meta[key] = (
                [x.strip() for x in inner.split(",") if x.strip()] if inner else []
            )
        else:
            meta[key] = val
    return meta


def parse(text: str) -> tuple[dict, str]:
    """解析文档：优先新定界，兼容旧 --- 头（迁移窗口）。"""
    if text.startswith(_OPEN + "\n"):
        end = text.find("\n" + _CLOSE + "\n", len(_OPEN) + 1)
        if end == -1:
            # 允许文件以 CLOSE 结尾且无后续正文换行
            alt = text.find("\n" + _CLOSE, len(_OPEN) + 1)
            if alt == -1:
                return {}, text
            header = text[len(_OPEN) + 1 : alt]
            body = text[alt + len("\n" + _CLOSE) :]
            if body.startswith("\n"):
                body = body[1:]
            return _parse_header_lines(header), body
        header = text[len(_OPEN) + 1 : end]
        body = text[end + len("\n" + _CLOSE + "\n") :]
        return _parse_header_lines(header), body

    if text.startswith(_LEGACY_DELIM + "\n"):
        end = text.find("\n" + _LEGACY_DELIM + "\n", len(_LEGACY_DELIM) + 1)
        if end == -1:
            return {}, text
        header = text[len(_LEGACY_DELIM) + 1 : end]
        body = text[end + len("\n" + _LEGACY_DELIM + "\n") :]
        return _parse_header_lines(header), body

    return {}, text


def dump(meta: dict, body: str) -> str:
    lines = [_OPEN]
    for key, val in meta.items():
        if isinstance(val, list):
            lines.append(f"{key}: [{', '.join(str(x) for x in val)}]")
        else:
            lines.append(f"{key}: {val}")
    lines.append(_CLOSE)
    header = "\n".join(lines)
    if not body.endswith("\n"):
        body += "\n"
    return header + "\n" + body
