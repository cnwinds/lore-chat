"""ImageGen：契约、failover、落盘 sink。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.engine.imagegen.backends import AgnesImagesBackend, BailianImagesBackend, OpenAIImagesBackend, _kind_from_http
from app.engine.imagegen.providers import (
    DuplicateImageProviderError,
    ImageGenProviderEntry,
    normalize_image_base_url,
    parse_image_providers,
    validate_image_providers_unique,
)
from app.engine.imagegen.sizes import OPENAI_SIZE
from app.engine.imagegen.service import ImageGen
from app.engine.imagegen.types import (
    GeneratedImage,
    ImageGenError,
    ImageGenErrorKind,
    ImageGenRequest,
)
from app.engine.kb_markdown_images import sanitize_markdown_image_srcs_for_storage
from app.engine.knowledge_writer import KnowledgeWriter
from app.models.cooldown import CooldownStore, image_cooldown_path_for_kb
from app.storage.repo import KnowledgeRepo


def _ig(tmp_path, providers: list[dict]) -> ImageGen:
    repo = KnowledgeRepo(tmp_path)
    writer = KnowledgeWriter(repo)
    settings = Settings(kb_path=tmp_path, image_providers=providers)
    store = CooldownStore(image_cooldown_path_for_kb(tmp_path))
    return ImageGen(settings, cooldown=store, knowledge_writer=writer)


def test_parse_and_validate_image_providers():
    entries = parse_image_providers(
        [
            {"provider": "openai", "api_key": "sk-a", "model": "dall-e-3"},
            {"id": "openai-2", "provider": "openai", "api_key": "sk-b", "model": "gpt-image-1"},
            {"provider": "zhipu", "api_key": "zk"},
            {"id": "openai-2", "provider": "openai", "api_key": "dup"},  # id 重复跳过
        ]
    )
    assert [e.id for e in entries] == ["openai", "openai-2", "zhipu"]
    assert entries[1].model == "gpt-image-1"
    with pytest.raises(DuplicateImageProviderError):
        validate_image_providers_unique(
            [
                {"id": "openai", "provider": "openai", "api_key": "a"},
                {"id": "openai", "provider": "openai", "api_key": "b"},
            ]
        )
    # 同厂家不同 id 合法
    validate_image_providers_unique(
        [
            {"id": "openai", "provider": "openai", "api_key": "a"},
            {"id": "openai-2", "provider": "openai", "api_key": "b"},
        ]
    )


def test_kind_from_http_safety_and_auth():
    assert _kind_from_http(401, "invalid api key") == ImageGenErrorKind.AUTH
    assert _kind_from_http(400, "content_policy_violation") == ImageGenErrorKind.SAFETY
    assert _kind_from_http(429, "rate limit") == ImageGenErrorKind.RATE_LIMIT
    assert _kind_from_http(503, "busy") == ImageGenErrorKind.TRANSIENT


def test_normalize_image_base_url_strips_full_endpoint():
    assert (
        normalize_image_base_url(
            "bailian",
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        )
        == "https://dashscope.aliyuncs.com"
    )
    assert (
        normalize_image_base_url(
            "zhipu",
            "https://open.bigmodel.cn/api/paas/v4/images/generations",
        )
        == "https://open.bigmodel.cn/api/paas/v4"
    )
    assert normalize_image_base_url("bailian", None) == "https://dashscope.aliyuncs.com"
    entry = ImageGenProviderEntry(
        id="bailian",
        provider="bailian",
        api_key="k",
        base_url="https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
    )
    assert entry.resolved_base_url() == "https://dashscope.aliyuncs.com"


@pytest.mark.asyncio
async def test_bailian_multimodal_for_qwen_and_wan27():
    entry = ImageGenProviderEntry(
        id="bailian",
        provider="bailian",
        api_key="sk-test",
        model="qwen-image-3.0-pro",
        base_url=(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/"
            "multimodal-generation/generation"
        ),
    )
    backend = BailianImagesBackend(entry)
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND"
        b"\xaeB`\x82"
    )
    create_resp = MagicMock()
    create_resp.status_code = 200
    create_resp.json.return_value = {
        "output": {"task_id": "t-qwen", "task_status": "PENDING"}
    }
    poll_resp = MagicMock()
    poll_resp.status_code = 200
    poll_resp.json.return_value = {
        "output": {
            "task_status": "SUCCEEDED",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": [{"image": "https://cdn.example/a.png"}],
                    },
                }
            ],
        }
    }
    dl_resp = MagicMock()
    dl_resp.status_code = 200
    dl_resp.content = png
    dl_resp.headers = {"content-type": "image/png"}

    with patch("app.engine.imagegen.backends.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=create_resp)
        client.get = AsyncMock(side_effect=[poll_resp, dl_resp])
        client_cls.return_value = client
        img = await backend.generate(ImageGenRequest(prompt="a cat", aspect_ratio="1:1"))

    assert img.data.startswith(b"\x89PNG")
    post_url = client.post.await_args.args[0]
    assert post_url == (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation"
    )
    body = client.post.await_args.kwargs["json"]
    assert body["model"] == "qwen-image-3.0-pro"
    assert body["input"]["messages"][0]["content"][0]["text"] == "a cat"
    assert body["parameters"]["size"] == "2048*2048"
    assert client.post.await_args.kwargs["headers"].get("X-DashScope-Async") == "enable"


@pytest.mark.asyncio
async def test_bailian_legacy_wanx_still_async_text2image():
    entry = ImageGenProviderEntry(
        id="bailian", provider="bailian", api_key="sk-test", model="wanx-v1"
    )
    backend = BailianImagesBackend(entry)
    png = b"\x89PNG\r\n\x1a\nfake"
    create_resp = MagicMock()
    create_resp.status_code = 200
    create_resp.json.return_value = {"output": {"task_id": "t1"}}
    poll_resp = MagicMock()
    poll_resp.status_code = 200
    poll_resp.json.return_value = {
        "output": {"task_status": "SUCCEEDED", "results": [{"url": "https://cdn.example/b.png"}]}
    }
    dl_resp = MagicMock()
    dl_resp.status_code = 200
    dl_resp.content = png
    dl_resp.headers = {"content-type": "image/png"}

    with patch("app.engine.imagegen.backends.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=create_resp)
        client.get = AsyncMock(side_effect=[poll_resp, dl_resp])
        client_cls.return_value = client
        img = await backend.generate(ImageGenRequest(prompt="x"))

    assert img.data.startswith(b"\x89PNG")
    assert client.post.await_args.args[0].endswith(
        "/api/v1/services/aigc/text2image/image-synthesis"
    )
    assert client.post.await_args.kwargs["headers"].get("X-DashScope-Async") == "enable"
    assert client.post.await_args.kwargs["json"]["input"] == {"prompt": "x"}


@pytest.mark.asyncio
async def test_openai_backend_b64(tmp_path):
    entry = ImageGenProviderEntry(
        id="openai", provider="openai", api_key="sk-test", model="dall-e-3"
    )
    backend = OpenAIImagesBackend(entry)
    import base64

    tiny = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND"
        b"\xaeB`\x82"
    ).decode()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"b64_json": tiny}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("app.engine.imagegen.backends.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=mock_resp)
        client_cls.return_value = client
        img = await backend.generate(ImageGenRequest(prompt="a cat"))
    assert img.data.startswith(b"\x89PNG")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        ImageGenErrorKind.SAFETY,
        ImageGenErrorKind.AUTH,
        ImageGenErrorKind.INVALID_REQUEST,
        ImageGenErrorKind.UNKNOWN,
    ],
)
async def test_non_failover_kinds_do_not_switch(tmp_path, kind):
    ig = _ig(
        tmp_path,
        [
            {"id": "openai", "provider": "openai", "api_key": "sk-a"},
            {"id": "zhipu", "provider": "zhipu", "api_key": "sk-b"},
        ],
    )
    calls = {"n": 0}

    async def boom(_req):
        calls["n"] += 1
        raise ImageGenError(f"err:{kind.value}", kind=kind)

    with patch(
        "app.engine.imagegen.router.build_backend",
        return_value=MagicMock(generate=AsyncMock(side_effect=boom)),
    ):
        with pytest.raises(ImageGenError) as ei:
            await ig.generate_bytes(ImageGenRequest(prompt="x"))
        assert ei.value.kind == kind
    assert calls["n"] == 1  # 未切到第二家
    if kind == ImageGenErrorKind.AUTH:
        assert not ig.cooldown.is_available("openai")
    else:
        assert ig.cooldown.is_available("openai")


@pytest.mark.asyncio
async def test_unexpected_exception_does_not_failover(tmp_path):
    ig = _ig(
        tmp_path,
        [
            {"id": "openai", "provider": "openai", "api_key": "sk-a"},
            {"id": "zhipu", "provider": "zhipu", "api_key": "sk-b"},
        ],
    )
    calls = {"n": 0}

    async def boom(_req):
        calls["n"] += 1
        raise RuntimeError("boom")

    with patch(
        "app.engine.imagegen.router.build_backend",
        return_value=MagicMock(generate=AsyncMock(side_effect=boom)),
    ):
        with pytest.raises(ImageGenError) as ei:
            await ig.generate_bytes(ImageGenRequest(prompt="x"))
        assert ei.value.kind == ImageGenErrorKind.UNKNOWN
    assert calls["n"] == 1
    assert ig.cooldown.is_available("openai")


@pytest.mark.asyncio
async def test_cancelled_error_propagates(tmp_path):
    import asyncio

    ig = _ig(
        tmp_path,
        [{"id": "openai", "provider": "openai", "api_key": "sk-a"}],
    )

    async def boom(_req):
        raise asyncio.CancelledError()

    with patch(
        "app.engine.imagegen.router.build_backend",
        return_value=MagicMock(generate=AsyncMock(side_effect=boom)),
    ):
        with pytest.raises(asyncio.CancelledError):
            await ig.generate_bytes(ImageGenRequest(prompt="x"))
    assert ig.cooldown.is_available("openai")


@pytest.mark.asyncio
async def test_failover_on_transient(tmp_path):
    ig = _ig(
        tmp_path,
        [
            {"id": "openai", "provider": "openai", "api_key": "sk-a"},
            {"id": "zhipu", "provider": "zhipu", "api_key": "sk-b"},
        ],
    )
    calls = {"n": 0}

    async def flaky(_req):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ImageGenError("503", kind=ImageGenErrorKind.TRANSIENT)
        return GeneratedImage(data=b"\x89PNG\r\n\x1a\nfake", extension="png")

    with patch(
        "app.engine.imagegen.router.build_backend",
        return_value=MagicMock(generate=AsyncMock(side_effect=flaky)),
    ):
        img = await ig.generate_bytes(ImageGenRequest(prompt="ok"))
    assert img.data.startswith(b"\x89PNG")
    assert calls["n"] == 2
    assert not ig.cooldown.is_available("openai")


def test_persist_chat_attachment_under_media_generated(tmp_path):
    ig = _ig(tmp_path, [])
    rel = ig.persist(
        GeneratedImage(data=b"not-really-png-but-ok", extension="png"),
        destination="chat_attachment",
    )
    assert rel.startswith("媒体/生成/")
    assert rel.endswith(".png")
    assert (tmp_path / rel).is_file()


def test_persist_kb_requires_directory_and_filename(tmp_path):
    ig = _ig(tmp_path, [])
    img = GeneratedImage(data=b"bytes", extension="png")
    with pytest.raises(ImageGenError) as e1:
        ig.persist(img, destination="kb", directory="assets", filename=None)
    assert e1.value.kind == ImageGenErrorKind.INVALID_REQUEST
    with pytest.raises(ImageGenError) as e2:
        ig.persist(img, destination="kb", directory=None, filename="a.png")
    assert e2.value.kind == ImageGenErrorKind.INVALID_REQUEST


def test_persist_kb_writes_path(tmp_path):
    ig = _ig(tmp_path, [])
    rel = ig.persist(
        GeneratedImage(data=b"kb-png", extension="png"),
        destination="kb",
        directory="assets/pics",
        filename="hero",
    )
    assert rel == "assets/pics/hero.png"
    assert (tmp_path / rel).read_bytes() == b"kb-png"


@pytest.mark.asyncio
async def test_tool_generate_image_not_configured(tmp_path):
    from app.engine.agent.tool_impl.image_tools import ImageGenTools

    ig = _ig(tmp_path, [])
    tools = ImageGenTools(ig)
    out = await tools.generate_image({"prompt": "x"})
    assert out.get("error") == "imagegen_not_configured"


def test_prefer_provider_soft_orders_then_keeps_rest():
    from app.engine.imagegen.router import select_image_provider

    settings = Settings(
        image_providers=[
            {"id": "openai", "provider": "openai", "api_key": "sk-a"},
            {"id": "zhipu", "provider": "zhipu", "api_key": "sk-b"},
            {"id": "bailian", "provider": "bailian", "api_key": "sk-c"},
        ]
    )
    store = CooldownStore("/tmp/unused-image-cooldown-prefer")
    sel = select_image_provider(settings, store, prefer_provider="zhipu")
    assert sel.entry.id == "zhipu"
    # 排除 zhipu 后应仍能选到 openai（链上其余条目仍在）
    sel2 = select_image_provider(
        settings, store, prefer_provider="zhipu", exclude_ids={"zhipu"}
    )
    assert sel2.entry.id == "openai"


def test_sanitize_markdown_restores_download_url():
    md = '见图 ![](/api/download?path=generated%2F2026%2Fa.png) 完'
    assert sanitize_markdown_image_srcs_for_storage(md) == (
        "见图 ![](generated/2026/a.png) 完"
    )


def test_sanitize_markdown_rejects_unrestorable_api_url():
    with pytest.raises(ValueError, match="/api/download"):
        sanitize_markdown_image_srcs_for_storage("![](/api/download)")


@pytest.mark.asyncio
async def test_tool_kb_destination_omits_attachments(tmp_path):
    from app.engine.agent.tool_impl.image_tools import ImageGenTools

    ig = _ig(
        tmp_path,
        [{"id": "openai", "provider": "openai", "api_key": "sk-a"}],
    )
    tools = ImageGenTools(ig)

    async def fake_bytes(_req, **_kw):
        return GeneratedImage(data=b"png", extension="png")

    with patch.object(ig, "generate_bytes", AsyncMock(side_effect=fake_bytes)):
        out = await tools.generate_image(
            {
                "prompt": "cat",
                "destination": "kb",
                "directory": "assets",
                "filename": "hero",
            }
        )
    assert out["rel_path"] == "assets/hero.png"
    assert "attachments" not in out
    assert (tmp_path / "assets/hero.png").read_bytes() == b"png"


def test_agnes_defaults_and_parse():
    entries = parse_image_providers(
        [{"provider": "agnes", "api_key": "ak-test", "model": "agnes-image-2.1-flash"}]
    )
    assert len(entries) == 1
    e = entries[0]
    assert e.provider == "agnes"
    assert e.resolved_model() == "agnes-image-2.1-flash"
    assert e.resolved_base_url() == "https://apihub.agnes-ai.com/v1"
    assert (
        normalize_image_base_url(
            "agnes", "https://apihub.agnes-ai.com/v1/images/generations"
        )
        == "https://apihub.agnes-ai.com/v1"
    )


@pytest.mark.asyncio
async def test_agnes_images_backend_uses_extra_body_and_return_base64(monkeypatch):
    """协议：文生图用顶层 return_base64；勿把 response_format 放顶层。"""
    import base64

    entry = ImageGenProviderEntry(
        id="agnes",
        provider="agnes",
        api_key="ak-test",
        model="agnes-image-2.1-flash",
    )
    backend = AgnesImagesBackend(entry)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
    captured: dict = {}

    class FakeResp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"created": 1, "data": [{"url": None, "b64_json": png}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    img = await backend.generate(ImageGenRequest(prompt="a cat", aspect_ratio="16:9"))
    assert img.extension == "png"
    assert img.data.startswith(b"\x89PNG")
    assert captured["url"].endswith("/images/generations")
    body = captured["json"]
    assert body["model"] == "agnes-image-2.1-flash"
    assert body["size"] == "1K"
    assert body["ratio"] == "16:9"
    assert body["return_base64"] is True
    assert "response_format" not in body  # 不可顶层
    assert "extra_body" not in body  # 文生图 Base64 无需 extra_body
