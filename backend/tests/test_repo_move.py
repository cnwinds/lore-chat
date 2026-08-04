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
