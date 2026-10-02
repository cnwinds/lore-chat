"""已激活 Skill 跨轮保留：按时间线里的 SKILL.md 读取记录，注入知识库当前正文。"""

from __future__ import annotations

from app.engine.agent import skill_activation
from app.engine.agent.skill_activation import (
    activated_skill_roots,
    active_skill_system_messages,
    build_active_skill_messages,
)

CATALOG = [
    {"root": "技能/a", "name": "skill-a", "description": "A", "entry": "技能/a/SKILL.md"},
    {"root": "技能/b", "name": "skill-b", "description": "B", "entry": "技能/b/SKILL.md"},
]


def _read(path: str, *, status: str = "done", error: str | None = None) -> dict:
    block = {
        "type": "tool",
        "tool": "read_doc",
        "status": status,
        "sources": [{"type": "kb", "path": path}],
    }
    if error:
        block["error"] = error
    return block


def _assistant(*blocks: dict) -> dict:
    return {"role": "assistant", "text": "ok", "timeline": list(blocks)}


def _conv(*messages: dict) -> dict:
    return {"id": "c1", "messages": list(messages)}


def test_roots_from_read_tool_name():
    conv = _conv(
        _assistant(
            {
                "type": "tool",
                "tool": "read",
                "status": "done",
                "sources": [{"type": "kb", "path": "技能/a/SKILL.md"}],
            }
        ),
    )
    assert activated_skill_roots(conv, CATALOG) == ["技能/a"]


def test_roots_from_skill_entry_reads_most_recent_first():
    conv = _conv(
        {"role": "user", "text": "q1"},
        _assistant(_read("技能/a/SKILL.md")),
        {"role": "user", "text": "q2"},
        _assistant(
            {"type": "parallel", "children": [_read("技能/b/SKILL.md")]},
        ),
    )
    assert activated_skill_roots(conv, CATALOG) == ["技能/b", "技能/a"]


def test_roots_ignore_non_entry_failed_and_disabled_reads():
    conv = _conv(
        _assistant(
            # 包内其它文件不算激活
            _read("技能/a/参考/数据字典.md"),
            # 读取失败 / 未完成不算
            _read("技能/b/SKILL.md", status="error"),
            _read("技能/b/SKILL.md", error="FileNotFoundError"),
            # 已停用（不在当前目录里）的包不再常驻
            _read("技能/gone/SKILL.md"),
        ),
    )
    assert activated_skill_roots(conv, CATALOG) == []


def test_roots_respect_lookback_window():
    conv = _conv(
        _assistant(_read("技能/a/SKILL.md")),
        _assistant(),
        _assistant(),
    )
    assert activated_skill_roots(conv, CATALOG, lookback=3) == ["技能/a"]
    assert activated_skill_roots(conv, CATALOG, lookback=2) == []


def test_active_messages_inject_current_body_and_skip_missing():
    bodies = {"技能/a/SKILL.md": "RULE A v2"}

    def read_body(path: str) -> str:
        if path not in bodies:
            raise FileNotFoundError(path)
        return bodies[path]

    msgs = build_active_skill_messages(CATALOG, ["技能/b", "技能/a"], read_body)
    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert content.startswith("【已激活 Skill】")
    assert "### skill-a · `技能/a`" in content
    assert "RULE A v2" in content
    assert "skill-b" not in content
    # 块名只列真正注入了正文的包
    assert msgs[0]["_parts"] == [
        {"kind": "skill_active", "label": "Skill「skill-a」", "text": content}
    ]


def test_active_messages_label_lists_every_injected_skill():
    msgs = build_active_skill_messages(
        CATALOG, ["技能/b", "技能/a"], lambda path: f"body of {path}"
    )
    assert msgs[0]["_parts"][0]["label"] == "Skill「skill-b、skill-a」"


def test_active_messages_empty_when_nothing_readable():
    def read_body(path: str) -> str:
        raise FileNotFoundError(path)

    assert build_active_skill_messages(CATALOG, ["技能/a"], read_body) == []
    assert build_active_skill_messages(CATALOG, [], read_body) == []


def test_active_messages_cap_per_skill_and_total(monkeypatch):
    monkeypatch.setattr(skill_activation, "ACTIVE_SKILL_MAX_CHARS", 10)
    monkeypatch.setattr(skill_activation, "ACTIVE_SKILL_TOTAL_CHARS", 15)
    catalog = CATALOG + [
        {"root": "技能/c", "name": "skill-c", "description": "C", "entry": "技能/c/SKILL.md"}
    ]
    msgs = build_active_skill_messages(
        catalog, ["技能/a", "技能/b", "技能/c"], lambda p: "x" * 30
    )
    content = msgs[0]["content"]
    assert "read uri=技能/a/SKILL.md offset=10" in content
    # 总预算剩 5 字给第二个包，第三个包放不下
    assert "read uri=技能/b/SKILL.md offset=5" in content
    assert "skill-c" not in content


def test_active_skill_system_messages_reads_repo_body():
    class _Doc:
        body = "BODY FROM KB"

    class _Repo:
        def read_doc(self, path: str):
            assert path == "技能/a/SKILL.md"
            return _Doc()

    conv = _conv(_assistant(_read("技能/a/SKILL.md")))
    msgs = active_skill_system_messages(conv, CATALOG, _Repo())
    assert "BODY FROM KB" in msgs[0]["content"]
    assert active_skill_system_messages(conv, [], _Repo()) == []
    assert active_skill_system_messages(None, CATALOG, _Repo()) == []
