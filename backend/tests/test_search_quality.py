from app.engine.search_quality import (
    HitMeta,
    classify_hit_strength,
    gate_page_hits,
    matched_signal_count,
)
from app.index.search_query import compile_search_query
from app.index.types import Hit


def test_matched_signal_count_phrase():
    assert matched_signal_count("Media Grant design doc", ("Media Grant", "不透明")) == 1


def test_gate_keeps_only_strong():
    compiled = compile_search_query("Media Grant 不透明")
    strong = Hit(doc_id="a", chunk="Media Grant 不透明设计", score=1.0, source="a.md")
    weak = Hit(doc_id="b", chunk="只有 URL 配置", score=1.0, source="b.md")
    meta = {
        "a": HitMeta(lane="kb_fts", fts_tier="strict"),
        "b": HitMeta(lane="conv_fts", fts_tier="relaxed"),
    }
    hits, strength = gate_page_hits(
        [strong, weak], meta, compiled=compiled, min_vector_score=0.5
    )
    assert strength == "strong"
    assert [h.doc_id for h in hits] == ["a"]


def test_classify_vector_strong():
    compiled = compile_search_query("docker")
    hit = Hit(doc_id="x", chunk="docker", score=0.9, source="x.md")
    meta = HitMeta(lane="kb_vector", vector_score=0.9)
    assert (
        classify_hit_strength(hit, meta, compiled=compiled, min_vector_score=0.5)
        == "strong"
    )
