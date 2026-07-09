from app.config import Settings


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
