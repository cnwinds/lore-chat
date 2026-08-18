from app.config import Settings


def test_settings_model_defaults_are_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_PATH", str(tmp_path / "knowledge"))
    monkeypatch.delenv("SMALL_MODEL", raising=False)
    monkeypatch.delenv("BIG_MODEL", raising=False)
    monkeypatch.delenv("EMBED_MODEL", raising=False)
    s = Settings()
    assert s.small_model == ""
    assert s.big_model == ""
    assert s.embed_model == ""
    assert s.chat_models == []
    assert s.utility_models == []
    assert s.embed_models == []


def test_settings_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_PATH", str(tmp_path / "knowledge"))
    monkeypatch.setenv("SMALL_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("BIG_MODEL", "gpt-4o")
    monkeypatch.setenv("EMBED_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    s = Settings()
    assert s.small_model == "gpt-4o-mini"
    assert s.big_model == "gpt-4o"
    assert s.embed_model == "text-embedding-3-small"
    assert str(s.kb_path).endswith("knowledge")
    assert s.agent_max_tool_calls == 25
    assert s.min_vector_score == 0.45
    assert s.edit_doc_max_edits == 10
    assert s.edit_doc_max_patch_chars == 8192
    assert s.edit_doc_require_read is True
    assert s.reindex_full_threshold == 4000
