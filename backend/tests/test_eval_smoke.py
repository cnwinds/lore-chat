import json

from app.config import Settings
from app.deps import build_container
from app.models.llm import FakeLLMClient


def test_second_similar_note_merges(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    d1 = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/docker/常用命令.md",
            "title": "常用命令",
            "category": "技术/docker",
            "tags": ["docker"],
            "ambiguous": False,
            "reason": "新主题",
        }
    )
    d2 = json.dumps(
        {
            "action": "merge",
            "rel_path": "技术/docker/常用命令.md",
            "title": "常用命令",
            "category": "技术/docker",
            "tags": ["docker"],
            "ambiguous": False,
            "reason": "同为 docker 命令",
        }
    )
    merged = "docker ps 查看容器\n\ndocker logs 查看日志\n"
    llm = FakeLLMClient(chat_responses=["摘要1", d1, "摘要2", d2, merged], embed_dim=8)
    c = build_container(settings, llm=llm)
    c.organizer.ingest_text("docker ps 查看容器")
    c.organizer.ingest_text("docker logs 查看日志")
    doc = c.repo.read_doc("技术/docker/常用命令.md")
    assert "docker ps" in doc.body and "docker logs" in doc.body
