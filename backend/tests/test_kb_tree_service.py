import pytest

from app.engine.enabled_skills import EnabledSkillsStore
from app.engine.kb_tree_service import KbTreeService
from app.engine.knowledge_writer import KbPathExistsError, KnowledgeWriter
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _svc(tmp_path, *, protected=("系统",), skills_dir="技能"):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=protected)
    llm = FakeLLMClient(embed_dim=8)
    idx = Indexer(VectorIndex(tmp_path / "vec"), FullTextIndex(tmp_path / "fts.db"), llm)
    writer = KnowledgeWriter(repo, idx, skills_dir=skills_dir)
    rev = IndexRevision(tmp_path / "revision.txt")
    return KbTreeService(repo, writer, rev, skills_dir=skills_dir), repo, rev


def test_import_upload_bumps_revision(tmp_path):
    svc, repo, rev = _svc(tmp_path)
    assert rev.get() == 0
    svc.import_upload(directory="技术", filename="a.md", data=b"# Hi\n\n")
    assert rev.get() == 1
    assert repo.read_doc("技术/a.md").body.startswith("# Hi")


def test_import_protected_directory(tmp_path):
    svc, _, _ = _svc(tmp_path)
    with pytest.raises(PermissionError, match="禁止写入"):
        svc.import_upload(directory="系统", filename="x.md", data=b"x\n")


def test_move_protected_target(tmp_path):
    svc, _, _ = _svc(tmp_path)
    svc.import_upload(directory="", filename="a.md", data=b"a\n")
    with pytest.raises(PermissionError, match="禁止移动"):
        svc.move(from_path="a.md", to_directory="系统")


def test_delete_no_bump_when_missing(tmp_path):
    svc, _, rev = _svc(tmp_path)
    with pytest.raises(FileNotFoundError):
        svc.delete("missing.md")
    assert rev.get() == 0


def test_delete_bumps_when_paths_removed(tmp_path):
    svc, _, rev = _svc(tmp_path)
    svc.import_upload(directory="x", filename="f.txt", data=b"hi")
    before = rev.get()
    r = svc.delete("x/f.txt")
    assert r["deleted_paths"] == ["x/f.txt"]
    assert rev.get() == before + 1


def test_discover_skills_clamped(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    svc.import_upload(
        directory="技能/pkg", filename="SKILL.md", data=b"# skill\n"
    )
    assert svc.discover_skills("") == ["技能/pkg"]
    assert svc.discover_skills("技能") == ["技能/pkg"]
    with pytest.raises(PermissionError, match="技能"):
        svc.discover_skills("其它")


def test_import_conflict(tmp_path):
    svc, _, _ = _svc(tmp_path)
    svc.import_upload(directory="", filename="a.md", data=b"x\n")
    with pytest.raises(KbPathExistsError):
        svc.import_upload(directory="", filename="a.md", data=b"y\n")


def test_import_skill_zip_unpacks(tmp_path):
    from app.engine.kb_pack import dump_pack_meta, pack_meta_for_directory

    import io
    import zipfile

    svc, repo, _ = _svc(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "lorechat-pack.json",
            dump_pack_meta(pack_meta_for_directory("技能/demo")),
        )
        zf.writestr("demo/SKILL.md", b"# skill\n")
        zf.writestr("demo/extra.txt", b"hi\n")
    result = svc.import_upload(
        directory="技能", filename="demo.zip", data=buf.getvalue()
    )
    assert result["kind"] == "skill_package"
    assert result["rel_path"] == "技能/demo"
    assert "技能/demo/SKILL.md" in repo.list_tree()
    assert "技能/demo/extra.txt" in repo.list_tree()
    assert "技能/demo.zip" not in repo.list_tree()


def test_import_uploads_bumps_revision_once(tmp_path):
    svc, repo, rev = _svc(tmp_path)
    assert rev.get() == 0
    out = svc.import_uploads(
        [
            ("课", "a.ipynb", b"{}"),
            ("课", "b.py", b"x=1\n"),
            ("课", "c.md", b"# c\n"),
        ]
    )
    assert rev.get() == 1
    assert [i["rel_path"] for i in out["items"]] == [
        "课/a.ipynb",
        "课/b.py",
        "课/c.md",
    ]
    assert repo.abs_path("课/a.ipynb").exists()


_SKILL_BODY = b"---\nname: demo\ndescription: Use demo.\n---\n\n# Demo\n"


def test_delete_skill_package_prunes_enabled_roots(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    svc.import_upload(directory="技能/keep", filename="SKILL.md", data=_SKILL_BODY)
    svc.import_upload(directory="技能/gone", filename="SKILL.md", data=_SKILL_BODY)
    store = EnabledSkillsStore(repo.root, skills_dir="技能")
    store.save_roots(["技能/keep", "技能/gone"])
    svc.delete("技能/gone")
    assert store.load_roots() == ["技能/keep"]


def test_delete_skill_md_prunes_package_root(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    svc.import_upload(directory="技能/gone", filename="SKILL.md", data=_SKILL_BODY)
    store = EnabledSkillsStore(repo.root, skills_dir="技能")
    store.save_roots(["技能/gone"])
    svc.delete("技能/gone/SKILL.md")
    assert store.load_roots() == []


def test_delete_unrelated_file_keeps_enabled_roots(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    svc.import_upload(directory="技能/keep", filename="SKILL.md", data=_SKILL_BODY)
    svc.import_upload(directory="笔记", filename="a.md", data=b"# a\n")
    store = EnabledSkillsStore(repo.root, skills_dir="技能")
    store.save_roots(["技能/keep"])
    svc.delete("笔记/a.md")
    assert store.load_roots() == ["技能/keep"]


def test_move_skill_package_remaps_enabled_root(tmp_path):
    svc, repo, _ = _svc(tmp_path)
    svc.import_upload(directory="技能/old-pkg", filename="SKILL.md", data=_SKILL_BODY)
    store = EnabledSkillsStore(repo.root, skills_dir="技能")
    store.save_roots(["技能/old-pkg"])
    svc.move(from_path="技能/old-pkg", to_directory="技能", to_filename="new-pkg")
    assert store.load_roots() == ["技能/new-pkg"]
