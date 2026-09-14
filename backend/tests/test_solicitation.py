from app.engine.agent.solicitation import parse_plaintext_solicitation
from app.engine.agent.tool_loop import AgentToolLoop
from app.models.llm import ChatWithToolsResult, ToolCall


SCREENSHOT_BODY = """方向已锁定「干净解谜」，我直接进入机制澄清。图标那边主人还没选，选项仍挂着不急。

解谜游戏的成败九成在「核心机制」——它决定每关谜题怎么生成。结合单机、单屏、极简美学的约束，我筛了四个最适配的机制族：

【征询】核心机制选哪个？（决定玩家每关「动」什么、谜题从哪来） 选项：推与序——Sokoban血统：网格上推方块到目标点，规则零学习成本，啊哈=想通推动顺序，关卡设计深度全在「序」；光与折——旋转镜面/棱镜把一束光引到目标，静态无计时，啊哈=找对反射路径，视觉天然适合双色极简；连与通——把散点按规则连成线或闭合回路（Flow/管线类），啊哈=全局观察后的豁然开朗；变与通——每走一步规则或重力翻转，玩家在「规则会变」中找出路，啊哈=意识到新规则即是钥匙；其他——我脑子里另有机制，说说看"""


def test_parse_screenshot_style_inline_options():
    parsed = parse_plaintext_solicitation(SCREENSHOT_BODY)
    assert parsed is not None
    assert parsed.question.startswith("核心机制选哪个？")
    assert [o["id"] for o in parsed.options] == [
        "opt1",
        "opt2",
        "opt3",
        "opt4",
        "opt5",
    ]
    assert parsed.options[0]["label"].startswith("推与序")
    assert parsed.options[-1]["label"].startswith("其他")
    assert "方向已锁定" in parsed.remainder
    assert "【征询】" not in parsed.remainder
    assert parsed.multi_select is False


def test_parse_numbered_options_after_marker():
    text = """先说结论。

【征询】先做哪一块？
1. 检索
2. 落库
3. 先问清楚范围"""
    parsed = parse_plaintext_solicitation(text)
    assert parsed is not None
    assert parsed.question == "先做哪一块？"
    assert [o["label"] for o in parsed.options] == [
        "检索",
        "落库",
        "先问清楚范围",
    ]
    assert parsed.remainder == "先说结论。"


def test_parse_history_report_format():
    text = """已通过 ask_user 向用户提问：选哪种节奏？
可选：慢；快"""
    parsed = parse_plaintext_solicitation(text)
    assert parsed is not None
    assert parsed.question == "选哪种节奏？"
    assert [o["label"] for o in parsed.options] == ["慢", "快"]
    assert parsed.remainder == ""


def test_parse_rejects_ordinary_numbered_advice():
    text = """建议如下：
1. 先做检索
2. 再落库
3. 最后归档"""
    assert parse_plaintext_solicitation(text) is None


def test_parse_rejects_single_option():
    text = "【征询】就这样？ 选项：好的"
    assert parse_plaintext_solicitation(text) is None


def test_parse_rejects_option_word_without_marker():
    text = "这个选项：不建议现在改架构。"
    assert parse_plaintext_solicitation(text) is None


def test_promote_injects_ask_user_when_no_tool_calls():
    result = ChatWithToolsResult(content=SCREENSHOT_BODY, tool_calls=[])
    next_result, remainder = AgentToolLoop._promote_plaintext_solicitation(result)
    assert remainder is not None
    assert "方向已锁定" in remainder
    assert len(next_result.tool_calls) == 1
    tc = next_result.tool_calls[0]
    assert tc.name == "ask_user"
    assert tc.arguments["question"].startswith("核心机制选哪个？")
    assert len(tc.arguments["options"]) == 5


def test_promote_skips_mixed_tool_round():
    result = ChatWithToolsResult(
        content=SCREENSHOT_BODY,
        tool_calls=[ToolCall(id="1", name="search_kb", arguments={"query": "x"})],
    )
    next_result, remainder = AgentToolLoop._promote_plaintext_solicitation(result)
    assert remainder is None
    assert next_result.tool_calls[0].name == "search_kb"


def test_promote_strips_duplicate_beside_real_ask_user():
    result = ChatWithToolsResult(
        content=SCREENSHOT_BODY,
        tool_calls=[
            ToolCall(
                id="1",
                name="ask_user",
                arguments={
                    "question": "核心机制选哪个？",
                    "options": [
                        {"id": "a", "label": "推与序"},
                        {"id": "b", "label": "光与折"},
                    ],
                },
            )
        ],
    )
    next_result, remainder = AgentToolLoop._promote_plaintext_solicitation(result)
    assert remainder is not None
    assert next_result.tool_calls[0].id == "1"
    assert "【征询】" not in (next_result.content or "")
