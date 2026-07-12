import pytest

from app.engine.patch import Edit, PatchError, apply_edits


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
