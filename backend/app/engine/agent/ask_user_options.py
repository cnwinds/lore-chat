"""ask_user 选项：离散标签 vs 需要用户自述。

根因：征询卡片只能提交现成标签。当某选项本身不是完整答案、
用户还得写出实质内容时，只提交标签会逼出多一轮「请再说一下」。

契约：
- ``options[].input = true`` 表示该项需要用户在卡片里填写
- 标签已经在邀请用户自述时，同样按 input 处理（兼容未标字段的旧调用）
- 决议可附 ``inputs[option_id] = 用户原文``；续聊文案为「标签：原文」
"""

from __future__ import annotations

import re
from typing import Any

# 原则：标签在邀请用户写出内容，而不是给出可直接采用的完整答案。
# 不用课程名/专名黑名单；只认「请用户自述」这类言语行为。
_INPUT_HINT = re.compile(
    r"我来描述|我来写|我来说|说说看|自己说|自己写|自行填写|自行描述|"
    r"自定义|补充说明|不限于|please specify|write your own|"
    r"^(其他|其它|Other)$|"
    r"^(其他|其它|Other)[（(—\-\s:：]"
)


def option_invites_input(label: str) -> bool:
    text = (label or "").strip()
    return bool(text and _INPUT_HINT.search(text))


def option_allows_input(option: dict | None) -> bool:
    if not isinstance(option, dict):
        return False
    if _coerce_input_flag(option.get("input")):
        return True
    return option_invites_input(str(option.get("label") or ""))


def normalize_ask_options(options: Any) -> list[dict]:
    """保留 id/label，并给需要自述的选项补上 input=true。"""
    if not isinstance(options, list):
        return []
    out: list[dict] = []
    for raw in options:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if item.get("id") is not None:
            item["id"] = str(item["id"])
        if item.get("label") is not None:
            item["label"] = str(item["label"])
        if option_allows_input(item):
            item["input"] = True
        else:
            item.pop("input", None)
        out.append(item)
    return out


def format_choice_texts(
    options: list | None,
    choice_ids: list[str],
    inputs: dict[str, str] | None = None,
) -> list[str]:
    by_id = {
        str(o.get("id")): o
        for o in (options or [])
        if isinstance(o, dict) and o.get("id") is not None
    }
    notes = {
        str(key): str(value).strip()
        for key, value in (inputs or {}).items()
        if str(value).strip()
    }
    texts: list[str] = []
    for cid in choice_ids:
        opt = by_id.get(str(cid))
        if not opt:
            continue
        label = str(opt.get("label") or cid)
        note = notes.get(str(cid), "")
        if note:
            texts.append(f"{label}：{note}")
        else:
            texts.append(label)
    return texts


def _coerce_input_flag(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return False


__all__ = [
    "format_choice_texts",
    "normalize_ask_options",
    "option_allows_input",
    "option_invites_input",
]
