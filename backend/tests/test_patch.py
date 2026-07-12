import pytest

from app.engine.patch import Edit, Insert, PatchError, apply_edits, apply_insert, diff_affected_range


def test_apply_edits_single_replace():
    body = "alpha\nbeta\ngamma\n"
    result = apply_edits(body, [Edit(old_string="beta\n", new_string="BETA\n")], max_patch_chars=8192)
    assert result.ok is True
    assert result.body == "alpha\nBETA\ngamma\n"
    assert result.applied == 1


def test_apply_edits_not_found():
    result = apply_edits("hello\n", [Edit(old_string="missing", new_string="x")], max_patch_chars=8192)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "NOT_FOUND"


def test_apply_edits_ambiguous():
    body = "foo bar\nfoo bar\n"
    result = apply_edits(
        body,
        [Edit(old_string="foo", new_string="baz")],
        max_patch_chars=8192,
    )
    assert result.ok is False
    assert result.error.code == "AMBIGUOUS"
    assert len(result.error.occurrences or []) == 2


def test_apply_edits_replace_all():
    body = "foo bar\nfoo bar\n"
    result = apply_edits(
        body,
        [Edit(old_string="foo", new_string="baz", replace_all=True)],
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert result.body == "baz bar\nbaz bar\n"
    assert result.applied == 1


def test_apply_edits_delete_with_empty_new_string():
    body = "keep\nremove me\nkeep\n"
    result = apply_edits(
        body,
        [Edit(old_string="remove me\n", new_string="")],
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert result.body == "keep\nkeep\n"


def test_apply_edits_too_large():
    big = "x" * 9000
    result = apply_edits("ok\n", [Edit(old_string="ok", new_string=big)], max_patch_chars=8192)
    assert result.ok is False
    assert result.error.code == "TOO_LARGE"


def test_apply_edits_newline_normalized():
    body = "line1\r\nline2\r\n"
    result = apply_edits(
        body,
        [Edit(old_string="line1\nline2\n", new_string="LINE1\nLINE2\n")],
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert "LINE1" in result.body
    assert "LINE2" in result.body


def test_apply_edits_sequential_multiple():
    body = "aaa\nbbb\nccc\n"
    result = apply_edits(
        body,
        [
            Edit(old_string="aaa\n", new_string="AAA\n"),
            Edit(old_string="ccc\n", new_string="CCC\n"),
        ],
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert result.body == "AAA\nbbb\nCCC\n"
    assert result.applied == 2


def test_apply_edits_affected_range():
    body = "aaa\nbbb\nccc\n"
    result = apply_edits(
        body,
        [Edit(old_string="bbb\n", new_string="BBB\n")],
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert result.affected_start == 4
    assert result.affected_end == 8


def test_apply_insert_after_heading():
    body = "# Title\n\n## 部署步骤\n原有内容\n"
    result = apply_insert(
        body,
        Insert(content="新增段落\n", after_heading="## 部署步骤"),
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert "新增段落" in result.body
    assert result.body.index("新增段落") > body.index("## 部署步骤")
    assert result.affected_start == body.index("原有内容")
    assert result.affected_end == result.affected_start


def test_apply_insert_at_offset():
    body = "abcdef"
    result = apply_insert(
        body,
        Insert(content="XY", at_offset=3),
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert result.body == "abcXYdef"
    assert result.affected_start == 3
    assert result.affected_end == 3


def test_apply_insert_append_default():
    body = "line\n"
    result = apply_insert(
        body,
        Insert(content="tail\n"),
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert result.body == "line\ntail\n"
    assert result.affected_start == len(body)
    assert result.affected_end == len(body)


def test_apply_insert_heading_not_found():
    result = apply_insert(
        "no headings\n",
        Insert(content="x", after_heading="## Missing"),
        max_patch_chars=8192,
    )
    assert result.ok is False
    assert result.error.code == "NOT_FOUND"


def test_apply_edits_not_found_has_hint():
    body = "alpha beta gamma\n"
    result = apply_edits(
        body,
        [Edit(old_string="alhpa", new_string="alpha")],
        max_patch_chars=8192,
    )
    assert result.ok is False
    assert result.error.hint
    assert "alpha" in result.error.hint


def test_diff_affected_range():
    old = "aaa\nbbb\nccc\n"
    new = "aaa\nBBB\nccc\n"
    start, end = diff_affected_range(old, new)
    assert start == 4
    assert end == 7


def test_diff_affected_range_unchanged():
    text = "same\n"
    assert diff_affected_range(text, text) == (None, None)
