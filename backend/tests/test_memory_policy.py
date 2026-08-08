from app.engine.memory.models import MemoryCandidate
from app.engine.memory.policy import (
    extraction_after_evidence_gate,
    rewrite_supported_by_evidence,
    validate_evidence,
)
from app.engine.memory.resolver import SlotAction, SlotResolver
from app.engine.memory.store import MemoryStore


def test_extraction_after_evidence_gate_counts_rejects():
    text = "我偏好简洁"
    good = MemoryCandidate(
        statement="我偏好简洁",
        category="preference",
        origin="direct",
        confidence=0.9,
        start_char=0,
        end_char=5,
    )
    bad = MemoryCandidate(
        statement="我偏好简洁",
        category="preference",
        origin="direct",
        confidence=0.9,
        start_char=10,
        end_char=15,
    )
    out = extraction_after_evidence_gate(text, [good, bad])
    assert len(out.candidates) == 1
    assert out.rejected_evidence_count == 1


def test_resolver_rejects_sensitive_without_auth(tmp_path):
    """原 observer 抽取拒计已废弃；敏感门槛由 SlotResolver + policy 覆盖。"""
    store = MemoryStore(tmp_path / "memory.db", owner_key="test")
    resolver = SlotResolver(store)
    out = resolver.apply(
        SlotAction(
            slot_key="identity.address",
            action="new",
            statement="我住在北京市朝阳区某某路100号",
            category="identity",
            origin="direct",
            confidence=0.9,
        ),
        conversation_id="c1",
    )
    assert out["ok"] is False
    assert out.get("error") == "rejected"
    assert store.list_confirmed() == []
    assert store.list_candidates() == []


def test_validate_evidence_accepts_rewritten_with_overlap():
    text = "我是一名软件工程师，主要致力于游戏服务器架构。"
    stmt = "我是一名软件工程师，专注游戏服务器架构设计。"
    cand = MemoryCandidate(
        statement=stmt,
        category="identity",
        origin="direct",
        confidence=0.9,
        start_char=0,
        end_char=len(text),
        rewritten=True,
    )
    assert validate_evidence(text, cand)


def test_validate_evidence_rejects_rewritten_without_overlap():
    text = "我其实更爱茶"
    cand = MemoryCandidate(
        statement="用户喜欢咖啡",
        category="preference",
        origin="inferred",
        confidence=0.7,
        start_char=0,
        end_char=len(text),
        rewritten=True,
    )
    assert not validate_evidence(text, cand)


def test_validate_evidence_rejects_short_evidence_for_rewrite():
    text = "我是后端"
    cand = MemoryCandidate(
        statement="我是后端工程师",
        category="identity",
        origin="direct",
        confidence=0.9,
        start_char=0,
        end_char=len(text),
        rewritten=True,
    )
    assert not validate_evidence(text, cand)


def test_rewrite_supported_by_evidence():
    assert rewrite_supported_by_evidence(
        "我是一名软件工程师，专注高并发",
        "我是一名软件工程师，主要致力于游戏服务器的高并发",
    )
    assert not rewrite_supported_by_evidence("用户喜欢咖啡", "我其实更爱茶")
