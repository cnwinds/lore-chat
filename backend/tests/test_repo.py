import shutil

import pytest
from app.storage.repo import KnowledgeRepo, Document


@pytest.fixture
def repo(tmp_path):
    return KnowledgeRepo(tmp_path / "knowledge")


def test_unquote_git_path_decodes_cjk():
    from app.storage.repo import unquote_git_path

    quoted = '"\\346\\212\\200\\350\\203\\275/douyin-transcript/SKILL.md"'
    assert unquote_git_path(quoted) == "技能/douyin-transcript/SKILL.md"
    assert unquote_git_path("技能/plain.md") == "技能/plain.md"


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
    assert "created" in doc.meta
    assert "updated" in doc.meta
    assert "docker ps" in doc.body


def test_write_doc_preserves_created_on_update(repo):
    repo.write_doc("a.md", {"title": "A"}, "v1\n", commit_msg="c1")
    created = repo.read_doc("a.md").meta["created"]
    repo.write_doc("a.md", {"title": "A"}, "v2\n", commit_msg="c2")
    doc = repo.read_doc("a.md")
    assert doc.meta["created"] == created
    assert doc.meta["updated"] >= created


def test_read_backfills_created_from_updated(repo):
    from app.storage import frontmatter

    path = repo.root / "legacy.md"
    path.write_text(
        frontmatter.dump({"title": "L", "updated": "2026-01-01T00:00:00"}, "body\n"),
        encoding="utf-8",
    )
    doc = repo.read_doc("legacy.md")
    assert doc.meta["created"] == "2026-01-01T00:00:00"


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
    (repo.root / ".gitkeep").write_text("", encoding="utf-8")
    tree = repo.list_tree()
    assert "技术/x.md" in tree and "生活/y.md" in tree
    assert ".gitkeep" not in tree


def test_write_and_read_bytes(repo):
    p = repo.write_bytes(
        "技术/docker/plan.pdf", b"%PDF-1.4 fake", commit_msg="add file"
    )
    assert p == "技术/docker/plan.pdf"
    assert repo.read_bytes(p) == b"%PDF-1.4 fake"


def test_list_and_read_revisions(repo):
    from app.storage.repo import revision_summary

    repo.write_doc("笔记/a.md", {"title": "A"}, "第一版\n", commit_msg="edit: 笔记/a.md")
    repo.write_doc("笔记/a.md", {"title": "A"}, "第二版\n", commit_msg="edit: 笔记/a.md")
    revs = repo.list_revisions("笔记/a.md")
    assert len(revs) >= 2
    assert revs[0]["message"] == "编辑"
    latest = repo.read_revision("笔记/a.md", revs[0]["sha"])
    older = repo.read_revision("笔记/a.md", revs[1]["sha"])
    assert latest["text"] == "第二版\n"
    assert older["text"] == "第一版\n"
    assert latest["binary"] is False
    assert revision_summary("refresh stock precepts", "系统/戒律.md") == "官方稿更新"
    assert revision_summary("merge official precepts", "系统/戒律.md") == "官方稿合并"
    assert revision_summary("confirm precepts merge", "系统/戒律.md") == "确认官方合并"
    assert revision_summary("apply official precepts", "系统/戒律.md") == "采用官方稿"


def test_parse_file_revision_log_skips_consecutive_blob():
    from app.storage.repo import parse_file_revision_log

    a = "a" * 40
    b = "b" * 40
    c = "c" * 40
    z = "0" * 40
    raw = (
        f"{a}\t1787838092\tedit: n.md\n"
        f":100644 100644 {z} {b} M\tn.md\n"
        f"\n"
        f"{'d' * 40}\t1787838093\tedit: n.md\n"
        f":100644 100644 {b} {b} M\tn.md\n"
        f"\n"
        f"{c}\t1787838094\tc3\n"
        f":100644 100644 {b} {'e' * 40} M\tn.md\n"
    )
    out = parse_file_revision_log(raw, rel_path="n.md", cap=80)
    assert [item["sha"] for item in out] == [a, c]
    assert out[0]["message"] == "编辑"
    assert out[0]["committed_at"] == "2026-08-27 21:41:32"


def test_list_revisions_skips_identical_blob(repo):
    repo.write_doc("n.md", {"title": "N"}, "same\n", commit_msg="c1")
    repo.write_doc("n.md", {"title": "N"}, "same\n", commit_msg="c2")
    revs = repo.list_revisions("n.md")
    assert len(revs) == 1


def test_read_revision_rejects_internal_and_bad_sha(repo):
    repo.write_bytes("脚本/run.py", b"print(1)\n", commit_msg="add")
    with pytest.raises(PermissionError):
        repo.list_revisions(".kb/changelog.md")
    with pytest.raises(ValueError, match="无效版本"):
        repo.read_revision("脚本/run.py", "../HEAD")
    py = repo.list_revisions("脚本/run.py")
    got = repo.read_revision("脚本/run.py", py[0]["short_sha"])
    assert got["text"] == "print(1)\n"


def test_read_revision_binary(repo):
    repo.write_bytes("图/a.bin", b"\x00\xff", commit_msg="bin")
    rev = repo.list_revisions("图/a.bin")[0]
    got = repo.read_revision("图/a.bin", rev["sha"])
    assert got["binary"] is True
    assert got["text"] is None


def test_concurrent_revision_reads_do_not_hang(repo):
    """FastAPI 线程池会并发打 git；GitPython cat-file 管道不能并行。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    repo.write_doc("n.md", {"title": "N"}, "第一版\n", commit_msg="c1")
    repo.write_doc("n.md", {"title": "N"}, "第二版\n", commit_msg="c2")

    def work():
        revs = repo.list_revisions("n.md")
        latest = repo.read_revision("n.md", revs[0]["sha"])
        older = repo.read_revision("n.md", revs[1]["sha"])
        return latest["text"], older["text"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(work) for _ in range(24)]
        for fut in as_completed(futs, timeout=15):
            assert fut.result() == ("第二版\n", "第一版\n")


def test_log_change_appends_changelog(repo):
    repo.log_change("创建 技术/x.md：docker 笔记", commit_msg="log")
    doc_text = (repo.root / ".kb" / "changelog.md").read_text(encoding="utf-8")
    assert "docker 笔记" in doc_text


def test_read_missing_doc_raises(repo):
    with pytest.raises(FileNotFoundError):
        repo.read_doc("nope.md")


def test_delete_doc(repo):
    repo.write_doc("projects/a/todo.md", {"title": "A"}, "body\n", commit_msg="add")
    deleted = repo.delete_path("projects/a/todo.md", commit_msg="delete")
    assert deleted == ["projects/a/todo.md"]
    with pytest.raises(FileNotFoundError):
        repo.read_doc("projects/a/todo.md")
    assert "projects/a/todo.md" not in repo.list_tree()


def test_delete_directory(repo):
    repo.write_doc("projects/mini-app/a.md", {"title": "A"}, "a\n", commit_msg="add")
    repo.write_doc("projects/mini-app/b.md", {"title": "B"}, "b\n", commit_msg="add")
    deleted = repo.delete_path("projects/mini-app", commit_msg="delete dir")
    assert set(deleted) == {"projects/mini-app/a.md", "projects/mini-app/b.md"}
    assert not (repo.root / "projects" / "mini-app").exists()


def test_move_directory(repo):
    repo.write_doc("projects/mini-app/a.md", {"title": "A"}, "a\n", commit_msg="add")
    repo.write_bytes(
        "projects/mini-app/x.pdf", b"pdf", commit_msg="add pdf"
    )
    old, new = repo.move_directory(
        "projects/mini-app", "archive/mini-app", commit_msg="move dir"
    )
    assert set(old) == {
        "projects/mini-app/a.md",
        "projects/mini-app/x.pdf",
    }
    assert set(new) == {
        "archive/mini-app/a.md",
        "archive/mini-app/x.pdf",
    }
    assert not (repo.root / "projects" / "mini-app").exists()
    assert not (repo.root / "projects").exists()
    assert (repo.root / "archive" / "mini-app" / "a.md").is_file()
    assert "archive/mini-app/a.md" in repo.list_tree()


def test_move_file(repo):
    repo.write_bytes("d/n.txt", b"hi", commit_msg="add")
    new = repo.move_file(
        "d/n.txt",
        "d/renamed.txt",
        commit_msg="rename",
    )
    assert new == "d/renamed.txt"
    assert repo.read_bytes(new) == b"hi"


def test_move_directory_allows_untracked_sidecar(repo):
    repo.write_doc("技能/pkg/SKILL.md", {"title": "S"}, "s\n", commit_msg="add")
    (repo.root / "技能" / "pkg" / "notes.txt").write_text("local\n", encoding="utf-8")
    old, new = repo.move_directory("技能/pkg", "技能/pkg2", commit_msg="rename pkg")
    assert "技能/pkg/SKILL.md" in old
    assert "技能/pkg2/SKILL.md" in new
    assert (repo.root / "技能" / "pkg2" / "SKILL.md").is_file()
    assert (repo.root / "技能" / "pkg2" / "notes.txt").is_file()
    assert not (repo.root / "技能" / "pkg").exists()


def test_list_revisions_follows_directory_rename(repo):
    repo.write_doc("技能/old-pkg/SKILL.md", {"title": "S"}, "第一版\n", commit_msg="c1")
    repo.write_doc("技能/old-pkg/SKILL.md", {"title": "S"}, "第二版\n", commit_msg="c2")
    repo.move_directory("技能/old-pkg", "技能/new-pkg", commit_msg="move dir")
    revs = repo.list_revisions("技能/new-pkg/SKILL.md")
    texts = [repo.read_revision("技能/new-pkg/SKILL.md", item["sha"])["text"] for item in revs]
    assert "第二版\n" in texts
    assert "第一版\n" in texts


def test_list_revisions_heals_uncommitted_directory_rename(repo):
    repo.write_doc(
        "技能/douyin-transcript/SKILL.md",
        {"title": "S"},
        "第一版\n",
        commit_msg="add skill",
    )
    repo.write_doc(
        "技能/douyin-transcript/SKILL.md",
        {"title": "S"},
        "第二版\n",
        commit_msg="edit skill",
    )
    shutil.move(
        str(repo.root / "技能" / "douyin-transcript"),
        str(repo.root / "技能" / "video-transcript"),
    )
    revs = repo.list_revisions("技能/video-transcript/SKILL.md")
    assert revs
    texts = [
        repo.read_revision("技能/video-transcript/SKILL.md", item["sha"])["text"]
        for item in revs
    ]
    assert "第二版\n" in texts
    assert "第一版\n" in texts


def test_move_file_untracked(repo):
    """工作区未 git add 的文件也可移动并纳入版本库。"""
    abs_p = repo.root / "orphan.bin"
    abs_p.write_bytes(b"\x00\x01")
    new = repo.move_file(
        "orphan.bin",
        "媒体/生成/2026-08/orphan.bin",
        commit_msg="move orphan",
    )
    assert new == "媒体/生成/2026-08/orphan.bin"
    assert repo.read_bytes(new) == b"\x00\x01"
    assert not abs_p.exists()
    assert "媒体/生成/2026-08/orphan.bin" in repo.list_tree()


def test_delete_protected_path_raises(repo):
    with pytest.raises(ValueError, match="禁止删除"):
        repo.delete_path(".kb/changelog.md", commit_msg="nope")


def test_delete_missing_raises(repo):
    with pytest.raises(FileNotFoundError):
        repo.delete_path("nope.md", commit_msg="nope")
