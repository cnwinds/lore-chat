from app.engine.agent.ask_user_options import (
    format_choice_texts,
    normalize_ask_options,
    option_allows_input,
    option_invites_input,
)


def test_invites_input_for_user_authored_labels():
    assert option_invites_input("其他（我来描述，不限于上面几类）")
    assert option_invites_input("其他——我脑子里另有机制，说说看")
    assert option_invites_input("其他")
    assert option_invites_input("Other (please specify)")


def test_complete_canned_labels_do_not_invite_input():
    assert not option_invites_input("研究分析（资料调研、数据整理、行业分析等）")
    assert not option_invites_input("A：重力翻转")
    assert not option_invites_input("其他方向的研究")


def test_explicit_input_flag_wins():
    assert option_allows_input({"id": "x", "label": "研究分析", "input": True})
    assert not option_allows_input({"id": "x", "label": "研究分析", "input": False})


def test_normalize_marks_inviting_labels():
    options = normalize_ask_options(
        [
            {"id": "research", "label": "研究分析"},
            {"id": "other", "label": "其他（我来描述）"},
            {"id": "flagged", "label": "研究分析", "input": True},
        ]
    )
    assert "input" not in options[0]
    assert options[1]["input"] is True
    assert options[2]["input"] is True


def test_format_choice_texts_appends_user_note():
    options = [
        {"id": "research", "label": "研究分析"},
        {"id": "other", "label": "其他（我来描述）", "input": True},
    ]
    assert format_choice_texts(options, ["research"]) == ["研究分析"]
    assert format_choice_texts(
        options, ["other"], {"other": " 陪伴写作 "}
    ) == ["其他（我来描述）：陪伴写作"]
    assert format_choice_texts(
        options, ["research", "other"], {"other": "陪伴写作"}
    ) == ["研究分析", "其他（我来描述）：陪伴写作"]


def test_ask_user_persists_input_flag(tmp_path):
    from app.engine.agent.tool_impl.interaction import InteractionTools
    from app.engine.pending import PendingStore

    tools = InteractionTools(PendingStore(tmp_path / "pending.json"))
    out = tools.ask_user(
        {
            "question": "这个角色主要负责什么方向？",
            "options": [
                {"id": "research", "label": "研究分析"},
                {"id": "other", "label": "其他（我来描述）"},
            ],
        }
    )
    by_id = {o["id"]: o for o in out["options"]}
    assert "input" not in by_id["research"]
    assert by_id["other"]["input"] is True
