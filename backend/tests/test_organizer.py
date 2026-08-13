from app.engine.organizer import Organizer
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.storage.repo import KnowledgeRepo
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.models.llm import FakeLLMClient
from tests.helpers import make_writer


def _make(tmp_path, chat_responses):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=chat_responses, embed_dim=8)
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    org = Organizer(
        repo=repo,
        retriever=retr,
        pending=pending,
        llm=llm,
        knowledge_writer=make_writer(repo, tmp_path),
    )
    return org, repo, pending


def test_ingest_rejects_question_only(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    result = org.ingest_text(
        "windows终端怎么设置utf8编码",
        forced_rel_path="技术/终端/编码.md",
    )
    assert result.status == "rejected"
    assert result.rel_path is None
    assert repo.list_tree() == []


def test_ingest_rejects_missing_path(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    result = org.ingest_text("可写入的内容", forced_rel_path="")
    assert result.status == "rejected"
    assert repo.list_tree() == []


def test_ingest_new_doc(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    result = org.ingest_text(
        "docker ps 用来查看容器",
        forced_rel_path="技术/docker/常用命令.md",
    )
    assert result.status == "saved"
    assert result.rel_path == "技术/docker/常用命令.md"
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker ps" in doc.body


def test_ingest_merge_into_existing(tmp_path):
    merged_body = "docker ps\n\ndocker logs 看日志\n"
    org, repo, pending = _make(tmp_path, [merged_body])
    repo.write_doc("技术/docker/常用命令.md", {"title": "常用命令"}, "docker ps\n", commit_msg="seed")
    org.writer.indexer.reindex_doc("技术/docker/常用命令.md", "docker ps\n")
    result = org.ingest_text(
        "docker logs 看日志",
        forced_rel_path="技术/docker/常用命令.md",
    )
    assert result.status == "saved"
    assert result.rel_path == "技术/docker/常用命令.md"
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker logs" in doc.body


def test_ingest_records_changelog(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    org.ingest_text("内容", forced_rel_path="笔记/a.md")
    changelog = (repo.root / ".kb" / "changelog.md").read_text(encoding="utf-8")
    assert "笔记/a.md" in changelog


def test_resolve_agent_choices_returns_continue(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    qid = pending.create(
        "选哪些内容？",
        [
            {"id": "basic", "label": "基本信息"},
            {"id": "progress", "label": "今日进展"},
        ],
        {"kind": "agent", "context": "lorechat 项目启动"},
        multi_select=True,
    )
    result = org.resolve_agent_choices(
        qid, ["basic", "progress"], conversation_context="用户：开始开发 lorechat"
    )
    assert result.status == "continue"
    assert result.continue_prompt
    assert "基本信息" in result.continue_prompt
    assert "开始开发 lorechat" in result.continue_prompt
    assert pending.get(qid)["status"] == "resolved"


def test_resolve_agent_done_after_write_acknowledges_path(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    qid = pending.create(
        "能补充一些细节吗？",
        [{"id": "done", "label": "就这样，够了"}],
        {
            "kind": "agent",
            "context": "已创建待办：小程序版本，保存在 projects/mini-app/version-todo.md",
        },
    )
    result = org.resolve_agent_choices(qid, ["done"])
    assert result.status == "saved"
    assert result.rel_path == "projects/mini-app/version-todo.md"
    assert "已记录到" in result.message


def test_resolve_agent_done_without_write_says_confirmed(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    qid = pending.create(
        "已足够，不需要改动？",
        [{"id": "done", "label": "已足够，不需要改动"}],
        {"kind": "agent", "context": "已有文档路径：projects/lorechat/start.md"},
    )
    result = org.resolve_agent_choices(qid, ["done"])
    assert result.status == "acknowledged"
    assert result.message == "好的，已确认。"


def test_ingest_forced_path_creates_new_file(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    result = org.ingest_text(
        "全新内容段落",
        forced_rel_path="技术/llm/指定路径.md",
    )
    assert result.status == "saved"
    assert result.rel_path == "技术/llm/指定路径.md"
    doc = repo.read_doc("技术/llm/指定路径.md")
    assert "全新内容段落" in doc.body


def test_legacy_pending_resolves_to_saved_without_kind(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    qid = pending.create(
        "记录哪部分？",
        [{"id": "a", "label": "要点 A"}],
        {"context": "背景说明"},
    )
    result = org.resolve_agent_choices(qid, ["a"])
    assert result.status == "saved"
    assert "要点 A" in result.message


def test_ingest_rejects_skill_md_outside_skills_dir(tmp_path):
    org, repo, _ = _make(tmp_path, [])
    result = org.ingest_text(
        "---\nname: x\n---\n\n# X\n",
        forced_rel_path="其它/demo/SKILL.md",
    )
    assert result.status == "rejected"
    assert "技能" in result.message


def test_ingest_skill_md_keeps_yaml_in_body(tmp_path):
    """Skill YAML 留在 body；不被 parse 进 KB meta；落盘用新定界。"""
    org, repo, _ = _make(tmp_path, [])
    new_body = "---\nname: demo\ndescription: x\n---\n\n# Demo\n\nbody\n"
    result = org.ingest_text(
        new_body,
        forced_rel_path="技能/demo/SKILL.md",
        meta={"title": "demo"},
    )
    assert result.status == "saved"
    doc = repo.read_doc("技能/demo/SKILL.md")
    assert "name: demo" in doc.body
    assert "description: x" in doc.body
    assert "# Demo" in doc.body
    assert "name" not in doc.meta
    assert "description" not in doc.meta
    assert doc.meta.get("title") == "demo"
    raw = repo.abs_path("技能/demo/SKILL.md").read_text(encoding="utf-8")
    assert raw.startswith("<<<LORE_META\n")
    assert "---\nname: demo" in raw


def test_update_doc_meta_preserves_skill_body(tmp_path):
    org, repo, _ = _make(tmp_path, [])
    body = "---\nname: demo\ndescription: x\n---\n\n# Demo\n"
    org.ingest_text(body, forced_rel_path="技能/demo/SKILL.md", meta={"title": "demo"})
    from app.engine.agent.tool_impl.kb_mutate import KbMutateTools
    from app.engine.agent.tool_impl.doc_read_guard import DocReadGuard
    from tests.helpers import make_writer

    tools = KbMutateTools(
        repo=repo,
        organizer=org,
        knowledge_writer=make_writer(repo, tmp_path),
        read_guard=DocReadGuard(require_read=False),
    )
    out = tools.update_doc_meta(
        {"path": "技能/demo/SKILL.md", "meta": {"tags": ["skill"]}}
    )
    assert out["status"] == "ok"
    doc = repo.read_doc("技能/demo/SKILL.md")
    assert doc.meta.get("tags") == ["skill"]
    assert doc.body.startswith("---\nname: demo")
    assert "description: x" in doc.body
    changelog = (repo.root / ".kb" / "changelog.md").read_text(encoding="utf-8")
    assert "更新元数据 技能/demo/SKILL.md" in changelog


def test_edit_doc_preserves_skill_yaml(tmp_path):
    org, repo, _ = _make(tmp_path, [])
    body = "---\nname: demo\ndescription: x\n---\n\n# Demo\n\nold line\n"
    org.ingest_text(body, forced_rel_path="技能/demo/SKILL.md", meta={"title": "demo"})
    from app.engine.agent.tool_impl.kb_mutate import KbMutateTools
    from app.engine.agent.tool_impl.doc_read_guard import DocReadGuard
    from tests.helpers import make_writer

    tools = KbMutateTools(
        repo=repo,
        organizer=org,
        knowledge_writer=make_writer(repo, tmp_path),
        read_guard=DocReadGuard(require_read=False),
    )
    out = tools.edit_doc(
        {
            "path": "技能/demo/SKILL.md",
            "edits": [{"old_string": "old line", "new_string": "new line"}],
        }
    )
    assert out.get("error") is None
    doc = repo.read_doc("技能/demo/SKILL.md")
    assert "name: demo" in doc.body
    assert "description: x" in doc.body
    assert "new line" in doc.body
    assert "old line" not in doc.body


def test_ingest_merge_existing_skill_keeps_yaml_when_llm_preserves(tmp_path):
    """已存在 SKILL.md 走 merge；FakeLLM 按合成契约回写保留 YAML。"""
    skill_yaml = "---\nname: demo\ndescription: x\n---\n"
    merged = skill_yaml + "\n# Demo\n\nmerged body\n"
    org, repo, _ = _make(tmp_path, [merged])
    repo.write_doc(
        "技能/demo/SKILL.md",
        {"title": "demo"},
        skill_yaml + "\n# Demo\n\nold\n",
        commit_msg="seed",
    )
    result = org.ingest_text(
        "补充一句",
        forced_rel_path="技能/demo/SKILL.md",
        write_mode="auto",
    )
    assert result.status == "saved"
    doc = repo.read_doc("技能/demo/SKILL.md")
    assert "name: demo" in doc.body
    assert "merged body" in doc.body


def test_reorganize_prompt_requires_preserving_body_yaml():
    from app.engine.document_synthesis import DocumentSynthesis
    from app.models.llm import FakeLLMClient

    llm = FakeLLMClient(
        chat_responses=["---\nname: demo\n---\n\n# ok\n"], embed_dim=8
    )
    synth = DocumentSynthesis(llm)
    out = synth.reorganize_existing(
        "---\nname: demo\n---\n\n# Old\n", "new bit", "demo"
    )
    assert "name: demo" in out
    sys_msg = llm.calls[-1]["messages"][0]["content"]
    assert "须原样保留" in sys_msg
    assert "YAML" in sys_msg
