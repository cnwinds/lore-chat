from __future__ import annotations


def source_dedupe_key(source: dict) -> str:
    st = source.get("type")
    if st == "kb":
        return f"kb:{source.get('path')}"
    if st == "conversation":
        return (
            f"conversation:{source.get('cid')}:{source.get('message_id')}:"
            f"{source.get('start_char')}:{source.get('end_char')}"
        )
    return f"{st}:{source.get('url')}"


def extend_sources(all_sources: list[dict], new_sources: list[dict]) -> None:
    seen = {source_dedupe_key(s) for s in all_sources}
    for s in new_sources:
        key = source_dedupe_key(s)
        if key not in seen:
            all_sources.append(s)
            seen.add(key)
