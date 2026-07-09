import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import deps
from app.models.llm import FakeLLMClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.config import Settings

    settings = Settings(kb_path=tmp_path / "knowledge")
    fake_decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/note.md",
            "title": "笔记",
            "category": "技术",
            "tags": ["t"],
            "ambiguous": False,
            "reason": "全新",
        }
    )
    llm = FakeLLMClient(chat_responses=["摘要", fake_decision] * 20, embed_dim=8)
    app = create_app(settings=settings, llm=llm)
    with TestClient(app) as client:
        yield client
