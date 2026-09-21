from app.engine.text_merge3 import has_conflict_markers, merge3


def test_clean_independent_line_edits():
    base = "A\nB\nC\n"
    ours = "A\nB-user\nC\n"
    theirs = "A-off\nB\nC\n"
    result = merge3(base, ours, theirs)
    assert result.clean
    assert result.text == "A-off\nB-user\nC\n"
    assert not result.conflicts
    assert not has_conflict_markers(result.text)


def test_take_theirs_when_ours_equals_base():
    result = merge3("A\nB\n", "A\nB\n", "A\nB2\n")
    assert result.clean
    assert result.text == "A\nB2\n"


def test_take_ours_when_theirs_equals_base():
    result = merge3("A\nB\n", "A\nB-user\n", "A\nB\n")
    assert result.clean
    assert result.text == "A\nB-user\n"


def test_identical_both_sides():
    result = merge3("A\n", "A\nX\n", "A\nX\n")
    assert result.clean
    assert result.text == "A\nX\n"


def test_conflict_same_line_keeps_ours_without_markers():
    result = merge3("A\nB\nC\n", "A\nB-user\nC\n", "A\nB-off\nC\n")
    assert not result.clean
    assert len(result.conflicts) == 1
    assert result.conflicts[0].ours == "B-user\n"
    assert result.conflicts[0].theirs == "B-off\n"
    assert result.text == "A\nB-user\nC\n"
    assert "<<<<<<<" not in result.text
    assert "<<<<<<<" in result.marked
    assert "B-off" in result.marked


def test_inserts_at_different_points_are_clean():
    result = merge3("A\nC\n", "A\nB\nC\n", "A\nC\nD\n")
    assert result.clean
    assert result.text == "A\nB\nC\nD\n"


def test_empty_base_two_way_conflicts():
    result = merge3("", "# 本地\n只说中文。\n", "# 官方\n只说英文。\n")
    assert not result.clean
    assert "<<<<<<<" not in result.text
    assert "只说中文" in result.text


def test_conflict_keeps_both_sides_trailing_inserts():
    """一侧改行、两侧都在其后追加：追加内容不得从冲突两侧丢失（穿插场景回归）。"""
    base = "A\nB\n"
    ours = "A\nB\n\n现行附录\n现行正文。\n"
    theirs = "A\nB2\n\n官方附录\n官方正文。\n"
    result = merge3(base, ours, theirs)
    assert not result.clean
    assert len(result.conflicts) == 1
    hunk = result.conflicts[0]
    assert "现行附录" in hunk.ours
    assert "现行正文" in hunk.ours
    assert "官方附录" in hunk.theirs
    assert "官方正文" in hunk.theirs
    # 结果稿采用 ours 视角，但必须铺满 ours 全文，不丢尾部
    assert result.text.endswith("现行附录\n现行正文。\n")


def test_ten_interleaved_edits_both_sides():
    """10+ 处穿插改动：每栏铺满各自文档、合并稿不丢任何一侧内容。"""
    base_lines = ["# 文档"]
    for n in range(1, 13):
        base_lines += [f"## {n}、第{n}节", f"基线正文 {n}。"]
    base = "\n".join(base_lines) + "\n"

    ours_lines = ["# 文档（现行）"]
    theirs_lines = ["# 文档（官方）"]
    for n in range(1, 13):
        section = f"## {n}、第{n}节"
        ours_lines += [section, f"基线正文 {n}。" if n % 2 == 0 else f"现行正文 {n}。"]
        theirs_lines += [section, f"官方正文 {n}。" if n % 2 == 0 else f"基线正文 {n}。"]
    ours_lines += ["", "## 十二、现行附录", "现行附录正文。"]
    theirs_lines += ["", "## 十二、官方附录", "官方附录正文。"]
    ours = "\n".join(ours_lines)
    theirs = "\n".join(theirs_lines)

    result = merge3(base, ours, theirs)
    # 奇偶节各自独改 → 干净并入；文首标题与文尾附录（含贴邻的第 12 节正文）双双冲突
    assert not result.clean
    assert len(result.conflicts) == 2
    tail_theirs = result.conflicts[-1].theirs
    for n in range(1, 13):
        assert f"## {n}、第{n}节" in result.text
        expected = f"现行正文 {n}。" if n % 2 else f"官方正文 {n}。"
        # 第 12 节正文与文尾追加锚点相接，聚进尾部冲突块
        assert expected in result.text or expected in tail_theirs
    assert "现行附录正文。" in result.text
