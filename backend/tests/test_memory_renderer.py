from app.engine.memory.renderer import MemoryRenderer
from app.storage.repo import KnowledgeRepo


def test_seed_and_render_includes_fact_marker(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    renderer = MemoryRenderer(repo, memory_rel="系统/记忆.md")
    renderer.ensure_seed()
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
    assert len(body) <= 4000
