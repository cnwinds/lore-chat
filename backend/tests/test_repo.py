import pytest
from app.storage.repo import KnowledgeRepo, Document


@pytest.fixture
def repo(tmp_path):
    return KnowledgeRepo(tmp_path / "knowledge")


def test_write_and_read_doc(repo):
    repo.write_doc(
        "技术/docker/常用命令.md",
        meta={"title": "常用命令", "tags": ["docker"]},
        body="docker ps\n",
        commit_msg="add docker note",
    )
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert isinstance(doc, Document)
    assert doc.meta["title"] == "常用命令"
    assert "docker ps" in doc.body


def test_write_creates_git_commit(repo):
    repo.write_doc("a.md", {"title": "A"}, "body\n", commit_msg="first")
    commits = list(repo.repo.iter_commits())
    assert any("first" in c.message for c in commits)


def test_append_doc(repo):
    repo.write_doc("a.md", {"title": "A"}, "line1\n", commit_msg="c1")
    repo.append_doc("a.md", "line2\n", commit_msg="c2")
    doc = repo.read_doc("a.md")
    assert "line1" in doc.body and "line2" in doc.body


def test_list_tree(repo):
    repo.write_doc("技术/x.md", {"title": "X"}, "b\n", commit_msg="c")
    repo.write_doc("生活/y.md", {"title": "Y"}, "b\n", commit_msg="c")
    tree = repo.list_tree()
    assert "技术/x.md" in tree and "生活/y.md" in tree


def test_save_and_get_attachment(repo):
    p = repo.save_attachment(
        "技术/docker", "plan.pdf", b"%PDF-1.4 fake", commit_msg="add file"
    )
    assert p == "技术/docker/attachments/plan.pdf"
    assert repo.get_attachment(p) == b"%PDF-1.4 fake"


def test_log_change_appends_changelog(repo):
    repo.log_change("创建 技术/x.md：docker 笔记", commit_msg="log")
    doc_text = (repo.root / ".kb" / "changelog.md").read_text(encoding="utf-8")
    assert "docker 笔记" in doc_text


def test_read_missing_doc_raises(repo):
    with pytest.raises(FileNotFoundError):
        repo.read_doc("nope.md")
