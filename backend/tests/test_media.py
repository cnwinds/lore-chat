"""多模态 media 物化与路由测试。"""

from __future__ import annotations

from pathlib import Path

from app.models.candidate import ModelCandidate
from app.models.media import (
    attachment_is_video,
    build_user_content_with_media,
    is_signed_media_file,
    is_video_file,
)
from app.models.router import select_candidate
from app.models.cooldown import CooldownStore


def _mp4_bytes() -> bytes:
    # minimal ftyp box
    return b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 8


def test_is_video_file_magic(tmp_path: Path):
    p = tmp_path / "clip.bin"
    p.write_bytes(_mp4_bytes())
    assert is_video_file(p) is True
    assert attachment_is_video("clip.bin", kb_path=tmp_path) is True


def test_signed_media_video(tmp_path: Path):
    p = tmp_path / "a.mp4"
    p.write_bytes(_mp4_bytes())
    assert is_signed_media_file(p) == "video"


def test_build_content_video_url_data_wire(tmp_path: Path):
    rel = "媒体/demo.mp4"
    (tmp_path / "媒体").mkdir()
    (tmp_path / rel).write_bytes(_mp4_bytes())

    cand = ModelCandidate(
        id="v",
        model="stealth/ox-alpha",
        api_key="k",
        base_url="https://example.com/v1",
        image=True,
        video=True,
        image_wire="data",
        video_wire="data",
    )
    content = build_user_content_with_media(
        "描述视频",
        [rel],
        candidate=cand,
        kb_path=tmp_path,
        public_base_url=None,
        signing_secret="sek",
    )
    assert isinstance(content, list)
    types = [p.get("type") for p in content]
    assert "video_url" in types
    video_part = next(p for p in content if p.get("type") == "video_url")
    assert str(video_part["video_url"]["url"]).startswith("data:video/")


def test_build_content_video_without_capability(tmp_path: Path):
    rel = "媒体/demo.mp4"
    (tmp_path / "媒体").mkdir()
    (tmp_path / rel).write_bytes(_mp4_bytes())

    cand = ModelCandidate(
        id="t",
        model="gpt",
        api_key="k",
        base_url="https://example.com/v1",
        image=False,
        video=False,
    )
    content = build_user_content_with_media(
        "看",
        [rel],
        candidate=cand,
        kb_path=tmp_path,
        public_base_url=None,
        signing_secret="sek",
    )
    assert isinstance(content, str)
    assert "未能送入模型" in content
    assert "demo.mp4" in content


def test_build_content_mixed_image_and_video(tmp_path: Path):
    rel_v = "媒体/demo.mp4"
    rel_i = "shot.png"
    (tmp_path / "媒体").mkdir()
    (tmp_path / rel_v).write_bytes(_mp4_bytes())
    (tmp_path / rel_i).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)

    cand = ModelCandidate(
        id="v",
        model="stealth/ox-alpha",
        api_key="k",
        base_url="https://example.com/v1",
        image=True,
        video=True,
    )
    content = build_user_content_with_media(
        "混合",
        [rel_i, rel_v],
        candidate=cand,
        kb_path=tmp_path,
        public_base_url=None,
        signing_secret="sek",
    )
    assert isinstance(content, list)
    types = [p.get("type") for p in content]
    assert types.count("image_url") == 1
    assert types.count("video_url") == 1


def test_bytes_look_like_video():
    from app.models.media import bytes_look_like_video

    assert bytes_look_like_video(_mp4_bytes(), name="x.bin") is True
    assert bytes_look_like_video(b"not video", name="readme.txt") is False


def test_lookup_qwen3_vl_has_video():
    from app.models.catalog import lookup_capabilities, reload_supplement_for_tests

    reload_supplement_for_tests()
    caps = lookup_capabilities("qwen/qwen3-vl-plus")
    assert caps.video is True


def test_lookup_ox_alpha_has_video():
    from app.models.catalog import lookup_capabilities, reload_supplement_for_tests

    reload_supplement_for_tests()
    caps = lookup_capabilities("stealth/ox-alpha")
    assert caps.video is True
    assert caps.image is True
    assert caps.max_videos == 1


def test_build_content_large_video_prefers_signed_url(tmp_path: Path):
    from app.models.media import MAX_VIDEO_DATA_WIRE_BYTES

    rel = "媒体/large.mp4"
    (tmp_path / "媒体").mkdir()
    chunk = _mp4_bytes()
    repeats = MAX_VIDEO_DATA_WIRE_BYTES // len(chunk) + 2
    (tmp_path / rel).write_bytes(chunk * repeats)

    cand = ModelCandidate(
        id="v",
        model="stealth/ox-alpha",
        api_key="k",
        base_url="https://example.com/v1",
        image=True,
        video=True,
        video_wire="data",
    )
    content = build_user_content_with_media(
        "描述",
        [rel],
        candidate=cand,
        kb_path=tmp_path,
        public_base_url="https://app.example.com",
        signing_secret="sek",
    )
    assert isinstance(content, list)
    video_part = next(p for p in content if p.get("type") == "video_url")
    url = str(video_part["video_url"]["url"])
    assert url.startswith("https://app.example.com/api/media/grant/")
    assert "token=" not in url


def test_build_content_small_video_uses_data_wire(tmp_path: Path):
    rel = "媒体/small.mp4"
    (tmp_path / "媒体").mkdir()
    (tmp_path / rel).write_bytes(_mp4_bytes())

    cand = ModelCandidate(
        id="v",
        model="stealth/ox-alpha",
        api_key="k",
        base_url="https://example.com/v1",
        image=True,
        video=True,
        video_wire="data",
    )
    content = build_user_content_with_media(
        "描述",
        [rel],
        candidate=cand,
        kb_path=tmp_path,
        public_base_url="https://app.example.com",
        signing_secret="sek",
    )
    assert isinstance(content, list)
    video_part = next(p for p in content if p.get("type") == "video_url")
    assert str(video_part["video_url"]["url"]).startswith("data:video/")


def test_build_content_dropped_videos_footnote(tmp_path: Path):
    paths = []
    (tmp_path / "媒体").mkdir()
    for i in range(2):
        rel = f"媒体/v{i}.mp4"
        (tmp_path / rel).write_bytes(_mp4_bytes())
        paths.append(rel)

    cand = ModelCandidate(
        id="v",
        model="stealth/ox-alpha",
        api_key="k",
        base_url="https://example.com/v1",
        image=True,
        video=True,
        max_videos=1,
    )
    content = build_user_content_with_media(
        "看",
        paths,
        candidate=cand,
        kb_path=tmp_path,
        public_base_url=None,
        signing_secret="sek",
    )
    assert isinstance(content, list)
    assert sum(1 for p in content if p.get("type") == "video_url") == 1
    text = next(p["text"] for p in content if p.get("type") == "text")
    assert "超出本消息上限" in text
    assert "v1.mp4" in text


def test_build_content_max_images_limit(tmp_path: Path):
    paths = []
    for i in range(3):
        rel = f"img{i}.png"
        (tmp_path / rel).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
        paths.append(rel)

    cand = ModelCandidate(
        id="v",
        model="gpt-4o",
        api_key="k",
        base_url="https://example.com/v1",
        image=True,
        video=False,
        max_images=2,
    )
    content = build_user_content_with_media(
        "看图",
        paths,
        candidate=cand,
        kb_path=tmp_path,
        public_base_url=None,
        signing_secret="sek",
    )
    assert isinstance(content, list)
    assert sum(1 for p in content if p.get("type") == "image_url") == 2
    text = next(p["text"] for p in content if p.get("type") == "text")
    assert "超出本消息上限" in text


def test_build_content_video_signed_url_wire(tmp_path: Path):
    rel = "媒体/demo.mp4"
    (tmp_path / "媒体").mkdir()
    (tmp_path / rel).write_bytes(_mp4_bytes())

    cand = ModelCandidate(
        id="v",
        model="stealth/ox-alpha",
        api_key="k",
        base_url="https://example.com/v1",
        image=True,
        video=True,
        video_wire="url",
    )
    content = build_user_content_with_media(
        "描述",
        [rel],
        candidate=cand,
        kb_path=tmp_path,
        public_base_url="https://app.example.com",
        signing_secret="sek",
    )
    assert isinstance(content, list)
    video_part = next(p for p in content if p.get("type") == "video_url")
    url = str(video_part["video_url"]["url"])
    assert url.startswith("https://app.example.com/api/media/grant/")
    assert "token=" not in url


def test_messages_need_video(tmp_path: Path):
    from app.models.llm import _messages_need_video

    rel = "媒体/demo.mp4"
    (tmp_path / "媒体").mkdir()
    (tmp_path / rel).write_bytes(_mp4_bytes())
    assert _messages_need_video(
        [{"role": "user", "attachments": [rel], "content": "x"}],
        kb_path=tmp_path,
    ) is True


def test_select_candidate_require_video(tmp_path: Path):
    from app.config import Settings

    s = Settings(
        kb_path=tmp_path,
        chat_models=[
            {
                "id": "no-v",
                "model": "gpt",
                "api_key": "k",
                "base_url": "https://example.com/v1",
                "image": True,
                "video": False,
            },
            {
                "id": "yes-v",
                "model": "stealth/ox-alpha",
                "api_key": "k",
                "base_url": "https://example.com/v1",
                "image": True,
                "video": True,
            },
        ],
    )
    store = CooldownStore(tmp_path / "cd.json")
    sel = select_candidate(s, "chat", store, require_video=True)
    assert sel.candidate.id == "yes-v"


def test_lookup_max_images_from_supplement():
    from app.models.catalog import lookup_capabilities, reload_supplement_for_tests

    reload_supplement_for_tests()
    caps = lookup_capabilities("gpt-4o")
    assert caps.max_images is None


def test_llm_select_with_video_attachment(tmp_path: Path):
    from app.config import Settings
    from app.models.llm import OpenAILLMClient

    rel = "媒体/demo.mp4"
    (tmp_path / "媒体").mkdir()
    (tmp_path / rel).write_bytes(_mp4_bytes())

    settings = Settings(
        kb_path=tmp_path,
        chat_models=[
            {
                "id": "no-v",
                "model": "gpt",
                "api_key": "k",
                "base_url": "https://example.com/v1",
                "image": True,
                "video": False,
            },
            {
                "id": "yes-v",
                "model": "stealth/ox-alpha",
                "api_key": "k",
                "base_url": "https://example.com/v1",
                "image": True,
                "video": True,
            },
        ],
    )
    client = OpenAILLMClient(settings)
    messages = [{"role": "user", "attachments": [rel], "content": "描述"}]
    sel = client._select(big=True, messages=messages)
    assert sel.candidate.id == "yes-v"
    assert sel.candidate.video is True
