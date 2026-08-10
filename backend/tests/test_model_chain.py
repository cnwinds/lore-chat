"""冷却、路由、迁移、目录能力。"""

from __future__ import annotations

import time

import pytest

from app.config import Settings
from app.models.candidate import ModelCandidate, migrate_settings_dict, resolve_chain_candidates
from app.models.catalog import lookup_capabilities
from app.models.cooldown import CooldownStore, ErrorClass, classify_error
from app.models.router import NoCandidateAvailable, select_candidate
from app.models.vision import sign_attachment_token, verify_attachment_token


def test_catalog_agnes_and_deepseek():
    a = lookup_capabilities("agnes-2.5-pro")
    assert a.image is True
    assert a.image_wire == "url"
    assert a.thinking is True
    d = lookup_capabilities("deepseek-v4-pro")
    assert d.image is False
    assert d.thinking is True
    unknown = lookup_capabilities("totally-unknown-model-xyz")
    assert unknown.image is False
    assert unknown.thinking is False


def test_migrate_settings_dict_from_legacy():
    data = migrate_settings_dict(
        {"big_model": "agnes-2.5-pro", "small_model": "gpt-4o-mini", "big_base_url": "https://apihub.agnes-ai.com/v1"}
    )
    assert data["chat_models"][0]["model"] == "agnes-2.5-pro"
    assert data["chat_models"][0]["image"] is True
    assert data["utility_models"][0]["model"] == "gpt-4o-mini"


def test_resolve_chain_from_legacy_settings(tmp_path):
    s = Settings(kb_path=tmp_path, big_model="gpt-4o", small_model="gpt-4o-mini", chat_models=[], utility_models=[])
    chat = resolve_chain_candidates(s, "chat")
    util = resolve_chain_candidates(s, "utility")
    assert chat[0].model == "gpt-4o"
    assert util[0].model == "gpt-4o-mini"


def test_classify_error():
    assert classify_error("rate limit exceeded") == ErrorClass.RATE_LIMIT
    assert classify_error("Error code: rate_limit_exceeded") == ErrorClass.RATE_LIMIT
    assert classify_error("RateLimitError: …") == ErrorClass.RATE_LIMIT
    assert classify_error("Invalid API Key") == ErrorClass.AUTH
    assert classify_error("connection timeout") == ErrorClass.TRANSIENT
    assert classify_error("model does not support image") == ErrorClass.CAPABILITY
    assert classify_error("model_not_found") == ErrorClass.CONFIG
    assert classify_error("The model `foo` does not exist") == ErrorClass.CONFIG
    # 勿把泛化文案误判
    assert classify_error("unsupported protocol") == ErrorClass.UNKNOWN
    assert classify_error("see image docs") == ErrorClass.UNKNOWN
    assert classify_error("insufficient permissions") == ErrorClass.UNKNOWN
    assert classify_error("file does not exist") == ErrorClass.UNKNOWN
    assert classify_error("insufficient_quota") == ErrorClass.RATE_LIMIT


def test_cooldown_exponential_and_independent(tmp_path):
    store = CooldownStore(tmp_path / "cd.json")
    now = 1_700_000_000.0
    h1 = store.record_failure("a", ErrorClass.TRANSIENT, now=now)
    assert h1.cooldown_until == now + 30
    h2 = store.record_failure("a", ErrorClass.TRANSIENT, now=now + 1)
    assert h2.cooldown_until == now + 1 + 60
    store.record_success("b")  # 不影响 a
    assert store.is_available("a", now=now + 1) is False
    assert store.get("a").cooldown_until == h2.cooldown_until


def test_auth_disables(tmp_path):
    store = CooldownStore(tmp_path / "cd.json")
    store.record_failure("x", ErrorClass.AUTH, error="401")
    assert store.get("x").disabled is True
    assert store.is_available("x") is False
    store.reenable("x")
    assert store.is_available("x") is True


def test_config_disables_and_clear_disabled(tmp_path):
    store = CooldownStore(tmp_path / "cd.json")
    store.record_failure("m", ErrorClass.CONFIG, error="404")
    assert store.get("m").disabled is True
    store.record_failure("r", ErrorClass.RATE_LIMIT, now=time.time())
    store.clear_disabled()
    assert store.get("m").disabled is False
    assert store.is_available("r") is False  # 限流冷却保留


def test_capability_skip_no_cooldown(tmp_path):
    store = CooldownStore(tmp_path / "cd.json")
    store.record_failure("v", ErrorClass.CAPABILITY, error="no vision")
    assert store.get("v").consecutive_failures == 0
    assert store.is_available("v") is True


def test_select_skips_no_image_and_failover(tmp_path):
    store = CooldownStore(tmp_path / "cd.json")
    s = Settings(
        kb_path=tmp_path,
        chat_models=[
            {"id": "primary", "model": "deepseek-v4-pro", "image": False, "thinking": True},
            {"id": "vision", "model": "gpt-4o", "image": True, "thinking": False},
        ],
    )
    sel = select_candidate(s, "chat", store, require_image=True)
    assert sel.candidate.id == "vision"
    # 仅因缺识图能力过滤，不算故障 failover
    assert sel.failover is False
    store.record_failure("vision", ErrorClass.RATE_LIMIT, now=time.time())
    with pytest.raises(NoCandidateAvailable):
        select_candidate(s, "chat", store, require_image=True)


def test_select_cooling_marks_failover(tmp_path):
    store = CooldownStore(tmp_path / "cd.json")
    s = Settings(
        kb_path=tmp_path,
        chat_models=[
            {"id": "a", "model": "m-a", "image": True, "thinking": False},
            {"id": "b", "model": "m-b", "image": True, "thinking": False},
        ],
    )
    store.record_failure("a", ErrorClass.TRANSIENT, now=time.time())
    sel = select_candidate(s, "chat", store)
    assert sel.candidate.id == "b"
    assert sel.failover is True


def test_url_wire_requires_public_base(tmp_path):
    store = CooldownStore(tmp_path / "cd.json")
    s = Settings(
        kb_path=tmp_path,
        public_base_url=None,
        chat_models=[
            {
                "id": "agnes",
                "model": "agnes-2.5-pro",
                "image": True,
                "image_wire": "url",
                "thinking": True,
            }
        ],
    )
    with pytest.raises(NoCandidateAvailable):
        select_candidate(s, "chat", store, require_image=True)
    s2 = s.model_copy(update={"public_base_url": "https://example.com"})
    sel = select_candidate(s2, "chat", store, require_image=True)
    assert sel.candidate.id == "agnes"
    assert sel.failover is False


def test_url_wire_skip_then_data_wire_not_failover(tmp_path):
    """首候选缺 public_base_url 时落到 data wire，不算故障 failover。"""
    store = CooldownStore(tmp_path / "cd.json")
    s = Settings(
        kb_path=tmp_path,
        public_base_url=None,
        chat_models=[
            {
                "id": "agnes",
                "model": "agnes-2.5-pro",
                "image": True,
                "image_wire": "url",
                "thinking": True,
            },
            {
                "id": "local",
                "model": "gpt-4o",
                "image": True,
                "image_wire": "data",
                "thinking": False,
            },
        ],
    )
    sel = select_candidate(s, "chat", store, require_image=True)
    assert sel.candidate.id == "local"
    assert sel.failover is False


def test_signed_token_roundtrip():
    tok = sign_attachment_token(rel_path="a/b.png", secret="sek", now=1000.0, ttl_sec=100)
    assert verify_attachment_token(rel_path="a/b.png", token=tok, secret="sek", now=1050.0)
    assert not verify_attachment_token(rel_path="a/b.png", token=tok, secret="sek", now=1200.0)
    assert not verify_attachment_token(rel_path="other.png", token=tok, secret="sek", now=1050.0)


def test_exclude_ids_enables_capability_failover(tmp_path):
    """缺能力失败不冷却时，exclude_ids 才能切到下一候选。"""
    store = CooldownStore(tmp_path / "cd.json")
    s = Settings(
        kb_path=tmp_path,
        chat_models=[
            {"id": "a", "model": "m-a", "image": True, "thinking": False},
            {"id": "b", "model": "m-b", "image": True, "thinking": False},
        ],
    )
    store.record_failure("a", ErrorClass.CAPABILITY, error="no vision")
    assert store.is_available("a") is True
    # 不排除 → 仍选 a
    assert select_candidate(s, "chat", store).candidate.id == "a"
    # 排除本轮失败 → 选 b
    sel = select_candidate(s, "chat", store, exclude_ids={"a"})
    assert sel.candidate.id == "b"
    assert sel.failover is True


def test_chat_capability_failover_uses_attempted_exclude(tmp_path):
    """CAPABILITY 不冷却：chat 须带 attempted exclude，否则会死循环在首候选。"""
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from app.models.llm import OpenAILLMClient

    store = CooldownStore(tmp_path / "cd.json")
    s = Settings(
        kb_path=tmp_path,
        chat_models=[
            {"id": "a", "model": "m-a", "image": True, "thinking": False},
            {"id": "b", "model": "m-b", "image": True, "thinking": False},
        ],
    )
    llm = OpenAILLMClient(s, cooldown=store)
    seen: list[str] = []

    def create(**kwargs):
        seen.append(kwargs["model"])
        if kwargs["model"] == "m-a":
            raise RuntimeError("model does not support image")
        msg = SimpleNamespace(content="ok", tool_calls=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=None,
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = create
    with patch.object(llm, "_client_for", return_value=mock_client):
        out = llm.chat([{"role": "user", "content": "hi"}], big=True)
    assert out == "ok"
    assert seen == ["m-a", "m-b"]
    assert llm.last_selection is not None
    assert llm.last_selection.candidate.id == "b"
    assert store.is_available("a") is True


def test_stream_capability_failover_before_output(tmp_path):
    """流式在未产出内容前 CAPABILITY 失败应切候选，而非死循环。"""
    from unittest.mock import MagicMock, patch

    from app.models.llm import OpenAILLMClient

    store = CooldownStore(tmp_path / "cd.json")
    s = Settings(
        kb_path=tmp_path,
        chat_models=[
            {"id": "a", "model": "m-a", "image": True, "thinking": False},
            {"id": "b", "model": "m-b", "image": True, "thinking": False},
        ],
    )
    llm = OpenAILLMClient(s, cooldown=store)
    seen: list[str] = []

    def create(**kwargs):
        seen.append(kwargs["model"])
        if kwargs["model"] == "m-a":
            raise RuntimeError("model does not support image")
        from tests.test_llm_stream import _chunk

        return iter([_chunk(content="hi", finish_reason="stop")])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = create
    with patch.object(llm, "_client_for", return_value=mock_client):
        chunks = list(
            llm.stream_chat_with_tools(
                [{"role": "user", "content": "x"}],
                [],
                big=True,
            )
        )
    # create 可能因 stream_options 回退再试一次，故 m-a 可出现多次
    assert seen[0] == "m-a"
    assert "m-b" in seen
    assert seen[-1] == "m-b"
    finals = [c for c in chunks if c.result is not None]
    assert finals[-1].result.content == "hi"
    assert finals[-1].candidate_id == "b"


def test_attachment_is_image_by_magic_without_suffix(tmp_path):
    from app.models.vision import attachment_is_image

    raw = tmp_path / "noext"
    raw.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    assert attachment_is_image("noext", kb_path=tmp_path) is True
    assert attachment_is_image("readme.txt", kb_path=tmp_path) is False


def test_signed_image_requires_magic_not_suffix(tmp_path):
    from app.models.vision import is_image_file, is_signed_image_file

    fake = tmp_path / "evil.png"
    fake.write_text("not an image")
    assert is_image_file(fake) is True  # 后缀启发式
    assert is_signed_image_file(fake) is False  # 签名出口必须 magic
    real = tmp_path / "ok.png"
    real.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    assert is_signed_image_file(real) is True


def test_model_routing_changed_ignores_effort_only():
    from app.models.candidate import model_routing_changed

    a = Settings(
        kb_path="/tmp",
        chat_models=[
            {
                "id": "a",
                "model": "m",
                "image": True,
                "image_wire": "data",
                "effort": "medium",
                "thinking": True,
                "thinking_protocol": "none",
            }
        ],
    )
    b = a.model_copy(
        update={
            "chat_models": [
                {
                    **a.chat_models[0],
                    "effort": "high",
                    "thinking_protocol": "deepseek",
                }
            ]
        }
    )
    assert model_routing_changed(a, b) is False
    c = a.model_copy(
        update={
            "chat_models": [
                {**a.chat_models[0], "model": "m2"},
            ]
        }
    )
    assert model_routing_changed(a, c) is True


def test_shared_cooldown_store_same_instance(tmp_path):
    from app.models.cooldown import shared_cooldown_store

    p = tmp_path / "cd.json"
    a = shared_cooldown_store(p)
    b = shared_cooldown_store(p)
    assert a is b
    a.record_failure("x", ErrorClass.AUTH)
    assert b.get("x").disabled is True
