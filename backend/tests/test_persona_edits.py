"""人设编辑纯函数（P2 · 任务 A）。"""

from app.engine.persona_edits import (
    EditPlan,
    owner_changes,
    plan_edits,
    texts_to_spans,
)


def test_owner_changes_add_replace_delete():
    base = "第一行\n第二行\n第三行\n"
    current = "第一行\n改写的第二行\n第四行\n"
    oc = owner_changes(base, current)
    assert oc.added_texts
    assert any("改写" in t for t in oc.added_texts)
    assert oc.removed_texts
    assert any("第二行" in t for t in oc.removed_texts)
    assert oc.protected_spans
    assert owner_changes("same", "same").protected_spans == []


def test_texts_to_spans_min_length():
    current = "abcd xyz abcd"
    assert texts_to_spans(current, ["ab"]) == []
    spans = texts_to_spans(current, ["abcd"])
    assert (0, 4) in spans
    assert (9, 13) in spans


def _plan(current: str, edits: list, **kw) -> EditPlan:
    return plan_edits(
        current,
        edits,
        card_refs=kw.get("card_refs", {"c1"}),
        memory_refs=kw.get("memory_refs", set()),
        protected_spans=kw.get("protected_spans", []),
        negative_texts=kw.get("negative_texts", []),
        secret_scan=kw.get("secret_scan", lambda _: False),
        max_edits=kw.get("max_edits", 8),
        text_max_chars=kw.get("text_max_chars", 600),
        max_total_chars=kw.get("max_total_chars", 6000),
        max_growth_chars=kw.get("max_growth_chars", 1200),
    )


def test_plan_replace_apply():
    current = "alpha\nbeta\ngamma\n"
    p = _plan(
        current,
        [
            {
                "op": "replace",
                "find": "beta",
                "text": "BETA",
                "basis": ["c1"],
                "reason": "r",
            }
        ],
    )
    assert len(p.applied) == 1
    assert p.body == "alpha\nBETA\ngamma\n"


def test_plan_delete_full_line():
    current = "a\nb\nc\n"
    p_b = _plan(
        current,
        [{"op": "delete", "find": "b", "basis": ["c1"], "reason": "r"}],
    )
    assert p_b.body == "a\nc\n"
    p_bnl = _plan(
        current,
        [{"op": "delete", "find": "b\n", "basis": ["c1"], "reason": "r"}],
    )
    assert p_bnl.body == "a\nc\n"
    last_no_nl = "a\nb\nc"
    p_last = _plan(
        last_no_nl,
        [{"op": "delete", "find": "c", "basis": ["c1"], "reason": "r"}],
    )
    assert p_last.body == "a\nb\n"


def test_plan_delete_inline():
    current = "xxbyy"
    p = _plan(
        current,
        [{"op": "delete", "find": "b", "basis": ["c1"], "reason": "r"}],
    )
    assert p.body == "xxyy"


def test_plan_insert_after_anchor():
    current = "line1\nline2\n"
    p = _plan(
        current,
        [
            {
                "op": "insert",
                "after": "line1",
                "text": "inserted",
                "basis": ["c1"],
                "reason": "r",
            }
        ],
    )
    assert p.body == "line1\ninserted\nline2\n"


def test_plan_insert_anchor_mid_line():
    current = "abc def\nnext\n"
    p = _plan(
        current,
        [
            {
                "op": "insert",
                "after": "abc",
                "text": "NEW",
                "basis": ["c1"],
                "reason": "r",
            }
        ],
    )
    assert p.body == "abc def\nNEW\nnext\n"


def test_plan_insert_after_last_line_no_trailing_nl():
    current = "first\nlast"
    p = _plan(
        current,
        [
            {
                "op": "insert",
                "after": "last",
                "text": "extra",
                "basis": ["c1"],
                "reason": "r",
            }
        ],
    )
    assert p.body == "first\nlast\nextra"


def test_plan_insert_empty_persona():
    p = _plan(
        "",
        [{"op": "insert", "after": "", "text": "hello", "basis": ["c1"], "reason": "r"}],
    )
    assert p.body == "hello"


def _append(text: str, after: str = "") -> dict:
    return {"op": "insert", "after": after, "text": text, "basis": ["c1"], "reason": "r"}


def test_plan_several_appends_on_empty_persona_keep_all_in_order():
    p = _plan("", [_append("A"), _append("B"), _append("C")])
    assert p.body == "A\nB\nC"
    assert [e.text for e in p.applied] == ["A", "B", "C"]
    assert p.dropped == []


def test_plan_several_appends_keep_order_and_trailing_newline():
    p = _plan("only\n", [_append("A"), _append("B")])
    assert p.body == "only\nA\nB\n"
    assert len(p.applied) == 2


def test_plan_anchor_on_last_line_counts_as_append():
    p = _plan("x\nlast\n", [_append("A", after="last"), _append("B")])
    assert p.body == "x\nlast\nA\nB\n"
    assert len(p.applied) == 2


def test_plan_append_with_mid_insert_and_replace():
    p = _plan(
        "a\nb\nc\n",
        [
            _append("END"),
            _append("MID", after="a"),
            {"op": "replace", "find": "c", "text": "C", "basis": ["c1"], "reason": "r"},
        ],
    )
    assert p.body == "a\nMID\nb\nC\nEND\n"


def test_plan_delete_last_line_then_append_leaves_no_blank_line():
    p = _plan(
        "人设\n第二行",
        [
            _append("新增段"),
            {"op": "delete", "find": "第二行", "basis": ["c1"], "reason": "r"},
        ],
    )
    assert p.body == "人设\n新增段\n"


def test_plan_span_covering_accepted_insert_point_is_overlap():
    p = _plan(
        "a\nb\n",
        [
            _append("NEW", after="a"),
            {"op": "delete", "find": "a", "basis": ["c1"], "reason": "r"},
        ],
    )
    assert p.body == "a\nNEW\nb\n"
    assert p.dropped == [{"index": 1, "reason": "overlap"}]


def test_plan_insert_append_trailing_newline():
    current = "only\n"
    p = _plan(
        current,
        [{"op": "insert", "after": "", "text": "tail", "basis": ["c1"], "reason": "r"}],
    )
    assert p.body == "only\ntail\n"
    p2 = _plan(
        "only",
        [{"op": "insert", "after": "", "text": "tail", "basis": ["c1"], "reason": "r"}],
    )
    assert p2.body == "only\ntail"


def test_plan_multi_edit_back_to_front():
    current = "A\nB\nC\n"
    p = _plan(
        current,
        [
            {"op": "replace", "find": "A", "text": "a", "basis": ["c1"], "reason": "1"},
            {"op": "replace", "find": "C", "text": "c", "basis": ["c1"], "reason": "2"},
        ],
    )
    assert p.body == "a\nB\nc\n"


def test_plan_replace_then_insert_no_research_collision():
    current = "X\nY\n"
    p = _plan(
        current,
        [
            {"op": "replace", "find": "X", "text": "x", "basis": ["c1"], "reason": "1"},
            {
                "op": "insert",
                "after": "Y",
                "text": "X again",
                "basis": ["c1"],
                "reason": "2",
            },
        ],
    )
    assert p.body == "x\nY\nX again\n"


def test_plan_replace_text_contains_other_find():
    current = "AAA\nBBB\n"
    p = _plan(
        current,
        [
            {"op": "replace", "find": "AAA", "text": "BBB", "basis": ["c1"], "reason": "1"},
            {"op": "replace", "find": "BBB", "text": "CCC", "basis": ["c1"], "reason": "2"},
        ],
    )
    assert p.body == "BBB\nCCC\n"  # 第二条 find 按 original 定位，不受第一条新文字干扰


def test_drop_reason_codes():
    current = "findme"
    base_edit = {"op": "replace", "find": "findme", "text": "x", "basis": ["c1"], "reason": ""}

    assert _plan(current, ["x"], max_edits=8).dropped[0]["reason"] == "bad_op"
    assert _plan(current, [{"op": "noop"}], max_edits=8).dropped[0]["reason"] == "bad_op"
    assert _plan(current, [base_edit] * 9, max_edits=8).dropped[-1]["reason"] == "bad_op"

    assert _plan(current, [{"op": "replace", "find": "f", "text": "  ", "basis": ["c1"]}]).dropped[0]["reason"] == "missing_text"
    assert _plan(current, [{"op": "delete", "find": "  ", "basis": ["c1"]}]).dropped[0]["reason"] == "missing_text"

    long = "x" * 601
    assert _plan(current, [{**base_edit, "text": long}]).dropped[0]["reason"] == "text_too_long"

    assert _plan(current, [{**base_edit, "find": "missing"}]).dropped[0]["reason"] == "not_found"
    amb = _plan("find x find", [{**base_edit, "find": "find"}])
    assert amb.dropped[0]["reason"] == "ambiguous"

    assert _plan(current, [{**base_edit, "basis": None}]).dropped[0]["reason"] == "no_basis"
    assert _plan(current, [{**base_edit, "basis": ["z9"]}]).dropped[0]["reason"] == "bad_basis"
    assert _plan(
        current,
        [{"op": "replace", "find": "findme", "text": "n", "basis": ["m1"], "reason": ""}],
        memory_refs={"m1"},
    ).dropped[0]["reason"] == "memory_basis_not_delete"
    assert _plan(
        current,
        [{"op": "insert", "after": "", "text": "n", "basis": ["m1"], "reason": ""}],
        memory_refs={"m1"},
    ).dropped[0]["reason"] == "memory_basis_not_delete"

    oc = owner_changes("", current)
    assert _plan(
        current,
        [base_edit],
        protected_spans=oc.protected_spans or [(0, len(current))],
    ).dropped[0]["reason"] == "protected"

    assert _plan(
        current,
        [{**base_edit, "text": "主人不要的新句子"}],
        negative_texts=["主人不要的新文句"],
    ).dropped[0]["reason"] == "tombstoned"

    assert _plan(current, [base_edit], secret_scan=lambda _: True).dropped[0]["reason"] == "secret"

    overlap = _plan(
        "hello",
        [
            {"op": "replace", "find": "hel", "text": "H", "basis": ["c1"], "reason": ""},
            {"op": "replace", "find": "ell", "text": "E", "basis": ["c1"], "reason": ""},
        ],
    )
    assert any(d["reason"] == "overlap" for d in overlap.dropped)

    assert _plan(
        current,
        [{"op": "insert", "after": "", "text": "extra", "basis": ["c1"], "reason": ""}],
        max_growth_chars=2,
    ).dropped[0]["reason"] == "growth_cap"

    assert _plan(
        current,
        [{**base_edit, "text": "muchlonger"}],
        max_total_chars=8,
    ).dropped[0]["reason"] == "total_cap"

    wipe = _plan(
        "x",
        [{"op": "delete", "find": "x", "basis": ["c1"], "reason": ""}],
    )
    assert wipe.applied == []
    assert any(d["reason"] == "would_empty" for d in wipe.dropped)


def test_tombstone_ratio_and_substring():
    current = "keep"
    neg = _plan(
        current,
        [{"op": "insert", "after": "", "text": "主人不要的新增句子", "basis": ["c1"], "reason": ""}],
        negative_texts=["主人不要的新增文句"],
    )
    assert neg.dropped[0]["reason"] == "tombstoned"

    sub = _plan(
        current,
        [{"op": "insert", "after": "", "text": "prefix 12345678 suffix", "basis": ["c1"], "reason": ""}],
        negative_texts=["12345678"],
    )
    assert sub.dropped[0]["reason"] == "tombstoned"

    ok = _plan(
        current,
        [{"op": "insert", "after": "", "text": "unrelated content", "basis": ["c1"], "reason": ""}],
        negative_texts=["totally different phrase here"],
    )
    assert len(ok.applied) == 1


def test_no_op_same_body():
    current = "same"
    p = _plan(
        current,
        [{"op": "replace", "find": "same", "text": "same", "basis": ["c1"], "reason": ""}],
    )
    assert p.applied == []
