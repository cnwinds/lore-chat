"""统一上下文视图：URI 解析与格式化。"""

import pytest

from app.engine.context_view.errors import InvalidUri
from app.engine.context_view.uri import format_uri, parse


def test_kb_bare_path_and_round_trip():
    u = parse("笔记/草稿.md")
    assert u.rel_path == "笔记/草稿.md"
    assert not u.is_dir
    assert format_uri(u) == "lore://kb/笔记/草稿.md"
    u2 = parse(format_uri(u))
    assert u2.rel_path == u.rel_path and u2.is_dir == u.is_dir


def test_kb_directory_trailing_slash():
    u = parse("lore://kb/技能/")
    assert u.is_dir
    assert u.rel_path == "技能"
    assert format_uri(u) == "lore://kb/技能/"


def test_kb_root_round_trip():
    u = parse("lore://kb/")
    assert u.rel_path == "" and u.is_dir
    assert format_uri(u) == "lore://kb/"


def test_reject_internal_kb():
    with pytest.raises(InvalidUri):
        parse(".kb/index/foo")
    with pytest.raises(InvalidUri):
        parse("lore://kb/.git/config")


def test_reject_dotdot():
    with pytest.raises(InvalidUri):
        parse("lore://kb/a/../b")


def test_conversations_dm_message():
    u = parse("lore://conversations/dm/default/abc123/msg1")
    assert u.bucket == "dm"
    assert u.owner == "default"
    assert u.conversation_id == "abc123"
    assert u.message_id == "msg1"
    assert format_uri(u) == "lore://conversations/dm/default/abc123/msg1"


def test_conversations_rooms_dir():
    u = parse("lore://conversations/rooms/cid1/")
    assert u.bucket == "rooms"
    assert u.conversation_id == "cid1"
    assert format_uri(u) == "lore://conversations/rooms/cid1/"


def test_memory_owner_kind():
    u = parse("lore://memory/owner/preference/slot1")
    assert u.scope_kind == "owner"
    assert u.kind == "preference"
    assert u.item_id == "slot1"
    assert format_uri(u) == "lore://memory/owner/preference/slot1"


def test_legacy_conversation_ref():
    ref = parse("conversation://cid9/m1")
    assert ref.conversation_id == "cid9"
    assert ref.message_id == "m1"


def test_unknown_scheme():
    with pytest.raises(InvalidUri):
        parse("http://example/kb/x")
