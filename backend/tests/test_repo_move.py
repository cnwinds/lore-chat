from app.storage.repo import KnowledgeRepo


def test_move_doc(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    repo.write_doc("a/one.md", {"title": "One"}, "hello\n", commit_msg="seed")
    new_path = repo.move_doc("a/one.md", "b/two.md", commit_msg="move")
    assert new_path == "b/two.md"
    assert repo.read_doc("b/two.md").body == "hello\n"
    try:
        repo.read_doc("a/one.md")
        raise AssertionError("old path should be gone")
    except FileNotFoundError:
        pass
    assert not (repo.root / "a").exists()


def test_move_doc_prunes_nested_empty_dirs(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    repo.write_doc(
        "zhangxuefeng-perspective/references/research/01.md",
        {"title": "R"},
        "x\n",
        commit_msg="seed",
    )
    repo.move_doc(
        "zhangxuefeng-perspective/references/research/01.md",
        "skill/张雪峰/references/research/01.md",
        commit_msg="move",
    )
    assert not (repo.root / "zhangxuefeng-perspective").exists()
    assert repo.read_doc("skill/张雪峰/references/research/01.md").body == "x\n"


def test_move_doc_keeps_parent_when_sibling_remains(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    repo.write_doc("a/one.md", {"title": "1"}, "1\n", commit_msg="c1")
    repo.write_doc("a/two.md", {"title": "2"}, "2\n", commit_msg="c2")
    repo.move_doc("a/one.md", "b/one.md", commit_msg="move")
    assert (repo.root / "a").is_dir()
    assert (repo.root / "a" / "two.md").is_file()
