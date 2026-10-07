from app.engine.memory.constants import MEMORY_PANEL_HINT
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
    body = renderer.render(facts)
    assert "## 偏好与沟通方式" in body
    assert "- 偏好简洁" in body
    assert "<!-- memory:01JTEST -->" in body
    assert MEMORY_PANEL_HINT in body
    assert len(body) <= 4000
    injected = MemoryRenderer.strip_for_injection(body)
    assert "<!-- memory:" not in injected
    assert "## 身份与稳定背景" not in injected
    again, ids = renderer.render_with_ids(facts)
    assert again == body
    assert ids == {"01JTEST"}


def test_render_with_ids_skips_lines_past_budget():
    core = {
        "id": "core",
        "category": "preference",
        "statement": "核心甲",
        "origin": "manual",
        "confidence": 1.0,
    }
    extra = {
        "id": "extra",
        "category": "preference",
        "statement": "溢出乙",
        "origin": "inferred",
        "confidence": 0.2,
    }
    full, ids = MemoryRenderer(max_chars=10**9).render_with_ids([core])
    assert ids == {"core"}
    body, kept = MemoryRenderer(max_chars=len(full)).render_with_ids([core, extra])
    assert kept == {"core"}
    assert "溢出乙" not in body
    assert "<!-- memory:core -->" in body
    stripped = MemoryRenderer.strip_for_injection(body)
    assert "<!-- memory:" not in stripped
    assert "核心甲" in stripped
