from app.engine.memory.session_extractor import compress_to_self_timeline


def test_compress_keeps_short_timeline_intact():
    msgs = ["我偏好中文", "帮我查一下天气"]
    out = compress_to_self_timeline(msgs, max_chars=5000)
    assert "[1] 我偏好中文" in out
    assert "[2] 帮我查一下天气" in out


def test_compress_prefers_self_narrative_when_over_budget():
    noise = ["这个问题怎么回答？"] * 40
    owner = ["我偏好用数据可视化替代插图，不使用 AI 生成图。"]
    msgs = noise[:20] + owner + noise[20:]
    out = compress_to_self_timeline(msgs, max_chars=400)
    assert "自述时间线" in out or "数据可视化" in out
    assert "数据可视化" in out
    # 大量纯提问应被优先丢掉
    assert out.count("这个问题怎么回答") <= 2
