import json

from app.config import Settings
from app.deps import build_container
from app.models.llm import FakeLLMClient


def test_second_similar_note_merges(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    merged = "docker ps 查看容器\n\ndocker logs 查看日志\n"
    llm = FakeLLMClient(chat_responses=[merged], embed_dim=8)
    c = build_container(settings, llm=llm)
    c.organizer.ingest_text(
        "docker ps 查看容器",
        forced_rel_path="技术/docker/常用命令.md",
    )
    c.organizer.ingest_text(
        "docker logs 查看日志",
        forced_rel_path="技术/docker/常用命令.md",
    )
    doc = c.repo.read_doc("技术/docker/常用命令.md")
    assert "docker ps" in doc.body and "docker logs" in doc.body
