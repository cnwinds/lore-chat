import pytest

from app.deps import build_container
from app.config import Settings


@pytest.fixture
def container(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir()
    settings = Settings(kb_path=kb)
    return build_container(settings)


@pytest.mark.asyncio
async def test_manage_memory_remember_renders_file(container):
    out = await container.agent.tools.execute(
        "manage_memory",
        {"action": "remember", "statement": "记住我偏好中文"},
    )
    assert out["ok"] is True
    doc = container.repo.read_doc("系统/记忆.md")
    assert "中文" in doc.body


@pytest.mark.asyncio
async def test_manage_memory_forget_by_fact_id(container):
    out = await container.agent.tools.execute(
        "manage_memory",
        {"action": "remember", "statement": "记住我喜欢跑步"},
    )
    fact_id = out["fact"]["id"]
    forget = await container.agent.tools.execute(
        "manage_memory",
        {"action": "forget", "fact_id": fact_id, "statement": ""},
    )
    assert forget["ok"] is True
    assert container.memory_service.store.list_confirmed() == []
