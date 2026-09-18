import io
import json
import zipfile

import pytest

from app.engine.kb_pack import (
    PACK_FORMAT,
    PackPathChoiceError,
    dump_pack_meta,
    original_unpack_path,
    pack_meta_for_directory,
    read_pack_meta,
    upload_unpack_path,
)


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_pack_meta_skill_and_directory():
    skill = pack_meta_for_directory("技能/职业规划/张雪峰")
    assert skill.kind == "skill"
    assert skill.rel_path == "技能/职业规划/张雪峰"
    assert skill.skills_rel == "职业规划/张雪峰"
    assert skill.name == "张雪峰"

    directory = pack_meta_for_directory("技术/文档")
    assert directory.kind == "directory"
    assert directory.rel_path == "技术/文档"
    assert directory.skills_rel == ""


def test_dump_and_read_pack_meta_roundtrip():
    meta = pack_meta_for_directory("技能/数数查询")
    data = _zip_bytes(
        {
            "lorechat-pack.json": dump_pack_meta(meta),
            "数数查询/SKILL.md": b"# skill\n",
        }
    )
    got = read_pack_meta(data)
    assert got == meta
    obj = json.loads(dump_pack_meta(meta))
    assert obj["format"] == PACK_FORMAT
    assert obj["kind"] == "skill"
    assert obj["skills_rel"] == "数数查询"


def test_read_pack_meta_missing_is_none():
    data = _zip_bytes({"数数查询/SKILL.md": b"# skill\n"})
    assert read_pack_meta(data) is None
    assert read_pack_meta(b"not-a-zip") is None
    assert read_pack_meta(b"") is None


def test_read_pack_meta_wrong_format_is_none():
    data = _zip_bytes(
        {
            "lorechat-pack.json": b'{"format": "other", "version": 1}\n',
        }
    )
    assert read_pack_meta(data) is None


def test_read_pack_meta_bad_json():
    data = _zip_bytes({"lorechat-pack.json": b"{not json"})
    with pytest.raises(ValueError, match="JSON"):
        read_pack_meta(data)


def test_read_pack_meta_rejects_oversized():
    from app.engine.kb_pack import MAX_PACK_META_BYTES

    data = _zip_bytes({"lorechat-pack.json": b"x" * (MAX_PACK_META_BYTES + 1)})
    with pytest.raises(ValueError, match="过大"):
        read_pack_meta(data)


def test_unpack_paths():
    skill = pack_meta_for_directory("技能/数数查询")
    assert original_unpack_path(skill, skills_dir="技能") == "技能/数数查询"
    nested = pack_meta_for_directory("技能/职业规划/张雪峰")
    assert original_unpack_path(nested, skills_dir="技能") == "技能/职业规划/张雪峰"
    other_skills = pack_meta_for_directory("技能/数数查询")
    assert original_unpack_path(other_skills, skills_dir="Skills") == "Skills/数数查询"
    directory = pack_meta_for_directory("技术/文档")
    assert original_unpack_path(directory, skills_dir="技能") == "技术/文档"
    assert upload_unpack_path(drop_dir="技能", filename="数数查询.zip") == "技能/数数查询"
    assert upload_unpack_path(drop_dir="", filename="文档.zip") == "文档"
    assert upload_unpack_path(drop_dir="笔记", filename="文档.zip") == "笔记/文档"


def test_pack_path_choice_error_defaults_to_upload():
    err = PackPathChoiceError(
        kind="skill",
        original_path="技能/数数查询",
        upload_path="技术/数数查询",
        skills_dir="技能",
    )
    assert err.default_path == "技术/数数查询"
    assert "技能/数数查询" in str(err)
    assert "技术/数数查询" in str(err)
