from app.engine.memory.renderer import MemoryRenderer


def test_render_includes_fact_marker_and_respects_max_chars():
    renderer = MemoryRenderer(max_chars=4000)
    facts = [
        {
            "id": "01JTEST",
            "category": "preference",
            "statement": "偏好简洁",
            "origin": "manual",
            "confidence": 1.0,
        }
    ]
    body = renderer.render(facts, revision=1)
    assert "## 偏好与沟通方式" in body
    assert "- 偏好简洁" in body
    assert "<!-- memory:01JTEST -->" in body
    assert "设置 → 记忆" in body
    assert len(body) <= 4000
    injected = MemoryRenderer.strip_for_injection(body)
    assert "<!-- memory:" not in injected
    assert "## 身份与稳定背景" not in injected
