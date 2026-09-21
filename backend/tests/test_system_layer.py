import re

import pytest

from app.engine.agent.prompts import build_system_prompt
from app.engine.agent.system_layer import SystemLayer
from app.engine.retriever import Retriever
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _repo(tmp_path):
    return KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))


def test_seeds_precepts_and_soul(tmp_path):
    repo = _repo(tmp_path)
    layer = SystemLayer(repo)
    assert "戒律" in repo.read_doc("系统/戒律.md").body
    assert "心法" in repo.read_doc("系统/心法.md").body
    # 出现在文档树中（可见），但归于系统目录
    assert "系统/戒律.md" in repo.list_tree()
    assert layer.prefix == "系统/"


def test_precepts_align_with_runtime_tools(tmp_path):
    """戒律须匹配现行行为原则，不堆工具参数，也不用旧名/口令黑名单。"""
    repo = _repo(tmp_path)
    SystemLayer(repo)
    body = repo.read_doc("系统/戒律.md").body
    assert "`write_doc`" in body
    assert "`write_kb_file`" in body
    assert "`manage_memory`" in body
    assert re.search(r"`write_kb`", body) is None
    assert "overwrite=true" not in body
    assert "`to_filename`" not in body
    assert "读写删已有条目用 `path`" not in body
    assert "口令不限字面" in body
    assert "不受本条阻挡" in body and "生图" in body
    # 写库门槛是一条原则（默认不沉淀 且 仅明确要求才写入），不是两条同义规则
    persist = re.search(r"## 一、落库（知识沉淀）\n(.*?)(?=\n## )", body, re.S)
    assert persist is not None
    persist_items = re.findall(
        r"(?ms)^(\d+)\. (.+?)(?=\n\d+\. |\Z)", persist.group(1)
    )
    assert len(persist_items) == 3
    gate = persist_items[0][1]
    assert "不把对话零散沉淀" in gate
    assert "仅当用户明确要求" in gate
    assert "口令不限字面" in gate
    assert "仅当用户明确要求" not in persist_items[1][1]
    assert "不确定是否该记" in persist_items[1][1]
    assert "不要自行拼接一篇再 `write_doc`" in body
    assert "系统会标记该会话已总结" in body
    assert "不再检索" not in body
    assert "优先依据总结文档" in body
    assert "无大纲则按 offset 续读" in body
    assert "可能截断，且不含图片等二进制" in body
    assert "不必为选路径再列一次目录" in body
    assert "局部编辑前须先读取目标区域" in body
    assert "非 Markdown 不得走文档局部编辑" in body
    assert "普通知识不得写入或移入" in body
    # 驻留/不检索/删除保护/用户修订生效是代码事实，不进提示词
    assert "系统控制层自身" not in body
    assert "不参与检索" not in body
    assert "不得自行删除或绕过" not in body
    assert "## 六、文档编辑" in body
    assert "## 七、目录规划" in body
    assert "## 八、用户生成 Skill" in body
    assert "## 九、无痕教学（陪伴学习）" in body
    assert "建构优先" in body
    assert "用户意愿最高" in body
    assert "纯事实查询、版本核实、故障排查" in body
    assert "写库与生成 Skill 的规矩写在本文件" in body
    assert "助手怎么做事" in body
    assert "不要抄进每个 SKILL.md" in body
    assert "不视为零散沉淀" in gate
    skill = re.search(
        r"## 八、用户生成 Skill\n(.*?)(?=\n## 九、|\Z)", body, re.S
    )
    assert skill is not None
    skill_items = re.findall(
        r"(?ms)^(\d+)\. (.+?)(?=\n\d+\. |\Z)", skill.group(1)
    )
    assert [n for n, _ in skill_items] == ["1", "2", "3", "4", "5", "6", "7"]
    teaching = re.search(
        r"## 九、无痕教学（陪伴学习）\n(.*?)\Z", body, re.S
    )
    assert teaching is not None
    teaching_items = re.findall(
        r"(?ms)^(\d+)\. (.+?)(?=\n\d+\. |\Z)", teaching.group(1)
    )
    assert [n for n, _ in teaching_items] == ["1", "2", "3", "4", "5"]
    assert "能固化则固化" in skill_items[2][1]
    assert "一套或有限几套可遵循的工作流程" in skill_items[2][1]
    assert "优先写成脚本" in skill_items[2][1]
    assert "输出用模板或结构约束" in skill_items[2][1]
    assert "若把这一步换成脚本或模板" in skill_items[2][1]
    assert "创建时划界" in skill_items[3][1]
    assert "哪些步骤可固化、哪些必须智能" in skill_items[3][1]
    assert "只靠模型发挥的提示词" in skill_items[3][1]
    assert "使用中自改进" in skill_items[5][1]
    assert "下一次按这个包做是否还会踩同一坑" in skill_items[5][1]
    assert "不要记成主人画像" in skill_items[5][1]
    assert "另写一篇知识" in skill_items[5][1]
    assert "多次结果漂移" in skill_items[5][1]
    assert "本轮流水账" in skill_items[6][1]
    assert "输出模板" in skill_items[6][1]
    assert "一次失败不得重写整包" in skill_items[6][1]
    from app.engine.agent.system_layer import _SUPERSEDED_PRECEPTS_HASHES

    assert (
        "f2af62e39cc708b42a2520891bfb313b9f66e562d78c954306466bd6183dd26a"
        in _SUPERSEDED_PRECEPTS_HASHES
    )
    assert (
        "6162e468eee05fbd613ef958cadca45872cad1b2ebdf503bfd1dcc1fca3fb737"
        in _SUPERSEDED_PRECEPTS_HASHES
    )
    assert (
        "bb90720c7925eaae9c235d25a0daa5b6337faa86024046151491ab0a17886373"
        in _SUPERSEDED_PRECEPTS_HASHES
    )
    assert (
        "14317525e79ab3791591e8ff6034c01d05dc2a49c18ac1cdb68d4ed0de5e4c0b"
        in _SUPERSEDED_PRECEPTS_HASHES
    )
    # YAML 触发头是 write_doc 契约，不进戒律
    assert "--- YAML" not in body
    assert "勿放进 meta" not in body
    assert "若本轮提供了沙箱工具" in body
    assert "跨段接续" in body
    assert "事实铁律（证据）" in body
    assert "详见事实铁律" not in body
    assert "用户所指的那段" in body
    assert "已给出时间、主题、标题" in body
    assert "不得改成「最近一段」交差" in body
    soul = repo.read_doc("系统/心法.md").body
    assert "默认指向本角色最近一段对话" in soul
    assert "先消解，仍不够再问" in soul


def test_system_layer_seeds_only_and_does_not_overwrite(tmp_path, monkeypatch):
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
    SystemLayer(repo)
    assert "旧官方播种稿" in repo.read_doc("系统/戒律.md").body

    repo.write_doc(
        "系统/戒律.md",
        {"title": "戒律"},
        "# 戒律\n用户修订不得覆盖。\n",
        commit_msg="user edit",
    )
    SystemLayer(repo)
    assert "用户修订不得覆盖" in repo.read_doc("系统/戒律.md").body


def test_compose_includes_both_files(tmp_path):
    layer = SystemLayer(_repo(tmp_path))
    text = layer.compose()
    assert "心法" in text and "戒律" in text
    # 心法（处世哲学）在前，戒律在后
    assert text.index("心法") < text.index("戒律")


def test_compose_reflects_edits_via_mtime(tmp_path):
    repo = _repo(tmp_path)
    layer = SystemLayer(repo)
    repo.write_doc("系统/戒律.md", {"title": "戒律"}, "# 新规约\n只答英文。\n", commit_msg="edit")
    assert "只答英文" in layer.compose()


def test_build_system_prompt_injects_layer():
    prompt = build_system_prompt("default", "【系统控制层内容XYZ】")
    assert "【系统控制层内容XYZ】" in prompt
    assert prompt.index("【系统控制层内容XYZ】") < prompt.index("lorechat")


def test_system_prompt_defers_skill_house_rules_to_precepts(tmp_path):
    from app.engine.agent.prompts import SYSTEM_PROMPT

    repo = _repo(tmp_path)
    SystemLayer(repo)
    precepts = repo.read_doc("系统/戒律.md").body
    assert "用户生成 Skill" in precepts or "## 八、用户生成 Skill" in precepts
    assert "事实铁律" not in SYSTEM_PROMPT
    assert "[Skill 目录]" not in SYSTEM_PROMPT
    assert "conversation://" in SYSTEM_PROMPT


def test_system_prompt_does_not_duplicate_tool_parameter_table():
    from app.engine.agent.prompts import SYSTEM_PROMPT

    assert "工具参数契约" not in SYSTEM_PROMPT
    assert "| write_doc |" not in SYSTEM_PROMPT
    assert "function 定义为准" in SYSTEM_PROMPT
    assert "## 事实铁律" not in SYSTEM_PROMPT


def test_build_system_prompt_web_on_affirms_search():
    prompt = build_system_prompt("default", web_enabled=True, search_configured=True)
    assert "本轮已开启联网搜索" in prompt
    assert "本轮未开启联网搜索" not in prompt
    assert "不要把单次失败或没有结果说成搜索未开启或功能不可用" in prompt


def test_build_system_prompt_web_off_denies_search():
    prompt = build_system_prompt("default", web_enabled=False, search_configured=True)
    assert "本轮未开启联网搜索" in prompt
    assert "本轮已开启联网搜索" not in prompt


def test_build_system_prompt_web_on_but_unconfigured():
    prompt = build_system_prompt("default", web_enabled=True, search_configured=False)
    assert "未配置搜索提供商" in prompt
    assert "本轮未开启联网搜索" not in prompt
    assert "本轮已开启联网搜索" not in prompt


def test_retriever_excludes_system_prefix(tmp_path):
    llm = FakeLLMClient(embed_dim=8)
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm, excluded_prefixes=("系统/",))
    idx.reindex_doc("系统/戒律.md", "默认不落库，渐进式披露读取资料")
    idx.reindex_doc("技术/note.md", "默认不落库，渐进式披露读取资料")
    hits = retr.search("渐进式披露", k=5).hits
    sources = {h.source for h in hits}
    assert "系统/戒律.md" not in sources


def test_system_dir_protected_from_delete(tmp_path):
    repo = _repo(tmp_path)
    SystemLayer(repo)
    with pytest.raises(ValueError):
        repo.delete_path("系统/戒律.md", commit_msg="try delete")
    with pytest.raises(ValueError):
        repo.delete_path("系统/", commit_msg="try delete dir")
