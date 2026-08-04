from app.engine.memory.models import ExtractionResult, MemoryCandidate
from app.engine.memory.observer import MemoryObserver
from app.engine.memory.policy import extraction_after_evidence_gate
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


def test_observer_includes_extractor_rejected_count(tmp_path):
    class FakeExtractor:
        def extract(self, text, *, context_messages=None):
            return ExtractionResult(candidates=[], rejected_evidence_count=2)

    store = MemoryStore(tmp_path / "memory.db", owner_key="test")
    obs = MemoryObserver(store, extractor=FakeExtractor())
    r = obs.observe_message("hello", conversation_id="c1", message_id="m1")
    assert r.rejected_count == 2
