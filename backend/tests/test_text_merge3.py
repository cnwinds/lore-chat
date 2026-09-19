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
