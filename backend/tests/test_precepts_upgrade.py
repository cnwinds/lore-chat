from app.engine.agent.system_layer import SystemLayer
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.precepts_upgrade import PreceptsUpgrade
from app.engine.text_merge3 import has_conflict_markers
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _repo(tmp_path):
    return KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))


def _upgrade(tmp_path, *, llm=None):
    repo = _repo(tmp_path)
    writer = KnowledgeWriter(repo, indexer=None)
    layer = SystemLayer(repo)
    return repo, writer, layer, PreceptsUpgrade(repo, writer, layer, llm=llm)


def _persist(writer, repo, body: str, msg: str = "edit precepts") -> None:
    doc = repo.read_doc("系统/戒律.md")
    writer.persist_document(
        "系统/戒律.md",
        doc.meta,
        body,
        commit_msg=msg,
        changelog_line="改戒律",
    )


def _bump_official(monkeypatch, sl, old_body: str, new_body: str) -> None:
    monkeypatch.setattr(sl, "_PRECEPTS_BODY", new_body)
    monkeypatch.setattr(
        sl,
        "_SUPERSEDED_PRECEPTS_HASHES",
        frozenset(set(sl._SUPERSEDED_PRECEPTS_HASHES) | {sl._seed_hash(old_body)}),
    )


def test_sync_writes_stock_when_live_is_official(tmp_path):
    repo, _writer, _layer, up = _upgrade(tmp_path)
    st = up.sync()
    assert st.status == "current"
    assert (repo.root / ".kb/precepts/stock.md").is_file()
    assert "口令不限字面" in (repo.root / ".kb/precepts/stock.md").read_text(
        encoding="utf-8"
    )


def test_unmodified_old_official_auto_upgrades(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo = _repo(tmp_path)
    old = "# 戒律 · 行为规约\n旧官方播种稿\n"
    repo.write_doc(
        "系统/戒律.md",
        {"title": "戒律 · 行为规约", "source": "system"},
        old,
        commit_msg="plant old stock",
    )
    monkeypatch.setattr(
        sl, "_SUPERSEDED_PRECEPTS_HASHES", frozenset({sl._seed_hash(old)})
    )
    writer = KnowledgeWriter(repo, indexer=None)
    layer = SystemLayer(repo)
    assert "旧官方播种稿" in repo.read_doc("系统/戒律.md").body
    up = PreceptsUpgrade(repo, writer, layer)
    st = up.sync()
    assert st.applied
    live = repo.read_doc("系统/戒律.md").body
    assert "旧官方播种稿" not in live
    assert "口令不限字面" in live
    assert not has_conflict_markers(live)


def test_clean_three_way_keeps_local_and_official(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo, writer, layer, up = _upgrade(tmp_path)
    up.sync()
    live = repo.read_doc("系统/戒律.md").body + "\n## 九、本地试验\n只说中文。\n"
    _persist(writer, repo, live)
    new_official = sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1)
    monkeypatch.setattr(sl, "_PRECEPTS_BODY", new_official)
    st = up.sync()
    assert st.status == "applied"
    body = repo.read_doc("系统/戒律.md").body
    assert "只说中文" in body
    assert "宁可先不记" in body
    assert not has_conflict_markers(body)
    assert sl._seed_hash((repo.root / ".kb/precepts/stock.md").read_text("utf-8")) == sl._seed_hash(
        new_official
    )
    assert "只说中文" in layer.compose()


def test_conflict_does_not_write_markers_and_keeps_live(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo, writer, _layer, up = _upgrade(tmp_path)
    up.sync()
    live = repo.read_doc("系统/戒律.md").body.replace("宁可不记", "必须先问用户", 1)
    _persist(writer, repo, live)
    monkeypatch.setattr(
        sl, "_PRECEPTS_BODY", sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1)
    )
    st = up.sync()
    assert st.status == "pending_review"
    assert st.pending
    assert st.pending["conflicts"]
    current = repo.read_doc("系统/戒律.md").body
    assert current == live
    assert not has_conflict_markers(current)
    assert "必须先问用户" in current
    assert "宁可先不记" not in current
    assert "必须先问用户" in st.pending["proposed"]


def test_no_stock_customized_is_two_way_review(tmp_path):
    repo = _repo(tmp_path)
    repo.write_doc(
        "系统/戒律.md",
        {"title": "戒律"},
        "# 戒律\n用户自己的家规。\n",
        commit_msg="custom",
    )
    writer = KnowledgeWriter(repo, indexer=None)
    layer = SystemLayer(repo)
    up = PreceptsUpgrade(repo, writer, layer)
    st = up.sync()
    assert st.status == "pending_review"
    assert "用户自己的家规" in repo.read_doc("系统/戒律.md").body
    assert not has_conflict_markers(repo.read_doc("系统/戒律.md").body)


def test_missing_stock_file_recovers_official_from_git(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo, writer, _layer, up = _upgrade(tmp_path)
    up.sync()
    seed = repo.read_doc("系统/戒律.md").body
    live = seed + "\n## 九、本地试验\n只说中文。\n"
    _persist(writer, repo, live)
    (repo.root / ".kb/precepts/stock.md").unlink()
    _bump_official(
        monkeypatch,
        sl,
        seed,
        sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1),
    )
    st = up.sync()
    assert st.status == "applied"
    body = repo.read_doc("系统/戒律.md").body
    assert "只说中文" in body
    assert "宁可先不记" in body
    assert "宁可不记" not in body
    assert sl._seed_hash(
        (repo.root / ".kb/precepts/stock.md").read_text(encoding="utf-8")
    ) == sl._seed_hash(sl._PRECEPTS_BODY)


def test_missing_stock_overlapping_edit_is_localized_conflict(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo, writer, _layer, up = _upgrade(tmp_path)
    up.sync()
    seed = repo.read_doc("系统/戒律.md").body
    live = seed.replace("宁可不记", "必须先问用户", 1)
    _persist(writer, repo, live)
    (repo.root / ".kb/precepts/stock.md").unlink()
    _bump_official(
        monkeypatch,
        sl,
        seed,
        sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1),
    )
    st = up.sync()
    assert st.status == "pending_review"
    assert st.pending["base"]
    hunks = st.pending["conflicts"]
    assert hunks
    assert hunks[0]["ours"] != st.pending["ours"]
    assert "必须先问用户" in hunks[0]["ours"]


def test_empty_base_pending_is_rebuilt_from_git_stock(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl
    import json

    repo, writer, _layer, up = _upgrade(tmp_path)
    up.sync()
    seed = repo.read_doc("系统/戒律.md").body
    live = seed.replace("宁可不记", "必须先问用户", 1)
    _persist(writer, repo, live)
    (repo.root / ".kb/precepts/stock.md").unlink()
    _bump_official(
        monkeypatch,
        sl,
        seed,
        sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1),
    )
    # 模拟旧逻辑：无祖先时把整篇当成一块冲突
    (repo.root / ".kb/precepts").mkdir(parents=True, exist_ok=True)
    (repo.root / ".kb/precepts/state.json").write_text(
        json.dumps(
            {
                "pending": {
                    "official_hash": sl._seed_hash(sl._PRECEPTS_BODY),
                    "ours": live,
                    "theirs": sl._PRECEPTS_BODY,
                    "base": "",
                    "proposed": live,
                    "proposed_source": "fallback",
                    "conflicts": [{"base": "", "ours": live, "theirs": sl._PRECEPTS_BODY}],
                    "created_at": "2026-09-20T00:00:00+08:00",
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    st = up.sync()
    assert st.status == "pending_review"
    assert st.pending["base"]
    assert st.pending["conflicts"][0]["ours"] != live


def test_confirm_writes_via_writer_and_updates_stock(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo, writer, _layer, up = _upgrade(tmp_path)
    up.sync()
    live = repo.read_doc("系统/戒律.md").body.replace("宁可不记", "必须先问用户", 1)
    _persist(writer, repo, live)
    monkeypatch.setattr(
        sl, "_PRECEPTS_BODY", sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1)
    )
    up.sync()
    merged = "# 戒律 · 行为规约\n必须先问用户；拿不准时宁可先不记。\n"
    st = up.confirm(merged)
    assert st.applied
    assert repo.read_doc("系统/戒律.md").body == merged
    assert "宁可先不记" in (repo.root / ".kb/precepts/stock.md").read_text(
        encoding="utf-8"
    )
    assert not (repo.root / ".kb/precepts/state.json").read_text("utf-8").strip() or (
        "pending" not in (repo.root / ".kb/precepts/state.json").read_text("utf-8")
        or '"pending": null' in (repo.root / ".kb/precepts/state.json").read_text("utf-8")
    )


def test_confirm_rejects_conflict_markers(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo, writer, _layer, up = _upgrade(tmp_path)
    up.sync()
    live = repo.read_doc("系统/戒律.md").body.replace("宁可不记", "必须先问用户", 1)
    _persist(writer, repo, live)
    monkeypatch.setattr(
        sl, "_PRECEPTS_BODY", sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1)
    )
    up.sync()
    try:
        up.confirm("<<<<<<< 当前\n坏\n>>>>>>> 新官方\n")
    except ValueError as exc:
        assert "冲突标记" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    assert "必须先问用户" in repo.read_doc("系统/戒律.md").body


def test_dismiss_keeps_live_and_skips_same_official(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo, writer, _layer, up = _upgrade(tmp_path)
    up.sync()
    live = repo.read_doc("系统/戒律.md").body.replace("宁可不记", "必须先问用户", 1)
    _persist(writer, repo, live)
    monkeypatch.setattr(
        sl, "_PRECEPTS_BODY", sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1)
    )
    up.sync()
    st = up.dismiss()
    assert st.status == "current"
    assert "必须先问用户" in repo.read_doc("系统/戒律.md").body
    again = up.sync()
    assert again.status == "current"
    assert again.pending is None


def test_propose_uses_llm_and_rejects_short_or_marked(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo, writer, layer, _ = _upgrade(tmp_path)
    up = PreceptsUpgrade(repo, writer, layer, llm=FakeLLMClient(chat_responses=["太短"]))
    up.sync()
    live = repo.read_doc("系统/戒律.md").body.replace("宁可不记", "必须先问用户", 1)
    _persist(writer, repo, live)
    monkeypatch.setattr(
        sl, "_PRECEPTS_BODY", sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1)
    )
    up.sync()
    fallback = up.status().pending["proposed"]
    st = up.propose()
    assert st.pending["proposed_source"] == "fallback"
    assert st.pending["proposed"] == fallback

    good = (fallback + "\n") * 2
    up.llm = FakeLLMClient(chat_responses=[good])
    st = up.propose()
    assert st.pending["proposed_source"] == "ai"
    assert st.pending["proposed"] == good.strip() or st.pending["proposed"] == good


def test_use_official_overwrites_live(tmp_path, monkeypatch):
    from app.engine.agent import system_layer as sl

    repo, writer, _layer, up = _upgrade(tmp_path)
    up.sync()
    _persist(writer, repo, "# 戒律\n本地。\n")
    new_official = sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1)
    monkeypatch.setattr(sl, "_PRECEPTS_BODY", new_official)
    st = up.use_official()
    assert st.applied
    assert "宁可先不记" in repo.read_doc("系统/戒律.md").body
    assert "本地。" not in repo.read_doc("系统/戒律.md").body
