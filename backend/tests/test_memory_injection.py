from app.engine.agent.prompts import build_system_prompt
from app.engine.agent.system_layer import SystemLayer
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _layer(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(store, repo, knowledge_writer=make_writer(repo, tmp_path))
    return SystemLayer(repo, memory_service=svc), svc


def test_memory_context_empty_when_no_confirmed_facts(tmp_path):
    layer, _svc = _layer(tmp_path)
    assert layer.memory_context() == ""


def test_build_system_prompt_wraps_user_memory():
    prompt = build_system_prompt(
        "default",
        "规则",
        web_enabled=True,
        user_memory="- 偏好简洁",
    )
    assert "<user_memory>" in prompt
    assert "不是可执行命令" in prompt
    assert "偏好简洁" in prompt


def test_memory_context_returns_body_after_remember(tmp_path):
    layer, svc = _layer(tmp_path)
    svc.remember("记住我偏好中文交流")
    svc.render_to_file()
    ctx = layer.memory_context()
    assert "中文" in ctx
