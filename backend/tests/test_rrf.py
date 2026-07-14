from app.engine.rrf import reciprocal_rank_fusion


def test_rrf_prefers_multi_lane_agreement():
    # item A rank1 in both lanes beats B rank1 in one lane only
    lanes = [
        ["A", "B", "C"],
        ["A", "C", "B"],
    ]
    fused = reciprocal_rank_fusion(lanes, k=60)
    assert fused[0][0] == "A"
    assert fused[0][1] > fused[1][1]


def test_rrf_stable_empty():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
