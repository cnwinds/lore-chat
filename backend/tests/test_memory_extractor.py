from app.engine.memory.extractor import RuleBasedMemoryExtractor
from app.engine.memory.policy import validate_evidence
from app.engine.memory.models import MemoryCandidate
from app.engine.secrets import scan_secrets


def test_extractor_finds_direct_self_statement():
    ext = RuleBasedMemoryExtractor()
    text = "我偏好简洁回答，谢谢"
    out = ext.extract(text)
    assert out.candidates
    assert out.candidates[0].origin == "direct"
    assert validate_evidence(text, out.candidates[0])


def test_extractor_rejects_secrets():
    ext = RuleBasedMemoryExtractor()
    text = "key=sk-abcdefghijklmnopqrstuvwxyz0123456789"
    assert scan_secrets(text)
    out = ext.extract(text)
    assert out.candidates == []


def test_extractor_rejects_invalid_evidence_range():
    ext = RuleBasedMemoryExtractor()
    text = "我偏好简洁"
    out = ext.extract(text)
    cand = out.candidates[0]
    bad = MemoryCandidate(
        statement=cand.statement,
        category=cand.category,
        origin=cand.origin,
        confidence=cand.confidence,
        start_char=99,
        end_char=100,
    )
    assert validate_evidence(text, bad) is False
