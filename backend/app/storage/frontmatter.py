from __future__ import annotations

_DELIM = "---"


def parse(text: str) -> tuple[dict, str]:
    if not text.startswith(_DELIM + "\n"):
        return {}, text
    end = text.find("\n" + _DELIM + "\n", len(_DELIM) + 1)
    if end == -1:
        return {}, text
    header = text[len(_DELIM) + 1 : end]
    body = text[end + len("\n" + _DELIM + "\n") :]
    meta: dict = {}
    for line in header.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            meta[key] = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
        else:
            meta[key] = val
    return meta, body


def dump(meta: dict, body: str) -> str:
    lines = [_DELIM]
    for key, val in meta.items():
        if isinstance(val, list):
            lines.append(f"{key}: [{', '.join(str(x) for x in val)}]")
        else:
            lines.append(f"{key}: {val}")
    lines.append(_DELIM)
    header = "\n".join(lines)
    if not body.endswith("\n"):
        body += "\n"
    return header + "\n" + body
