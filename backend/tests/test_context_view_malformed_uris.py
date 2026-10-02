"""畸形 lore:// 输入须返回 error 字典，不得抛未捕获异常。"""

from __future__ import annotations

import pytest

from tests.test_context_view_tools_common import cv_env  # noqa: F401

_MALFORMED = [
    "lore://memory/owner/not_a_real_kind/",
    "lore://conversations/unknown_bucket/",
    "lore://memory/owner/preference/f1/extra",
    "lore://kb/foo/../bar.md",
    "lore://memory/role//practice/",
    "lore://memory/persona/" + "x" * 400 + "/",
    "",
    "lore://",
    "not a uri at all",
]


@pytest.mark.parametrize("uri", _MALFORMED)
def test_search_never_raises(cv_env, uri):
    args: dict = {"query": "test"}
    if uri:
        args["paths"] = [uri]
    out = cv_env.tools.search(args)
    assert isinstance(out, dict)
    assert "summary" in out


@pytest.mark.parametrize("uri", _MALFORMED)
def test_read_never_raises(cv_env, uri):
    if not uri:
        out = cv_env.tools.read({"uri": ""})
    else:
        out = cv_env.tools.read({"uri": uri})
    assert isinstance(out, dict)
    assert "error" in out or "summary" in out


@pytest.mark.parametrize("uri", _MALFORMED)
def test_list_never_raises(cv_env, uri):
    if uri == "":
        out = cv_env.tools.list({"uri": ""})
    elif uri == "lore://":
        out = cv_env.tools.list({"uri": "lore://"})
    else:
        out = cv_env.tools.list({"uri": uri})
    assert isinstance(out, dict)
