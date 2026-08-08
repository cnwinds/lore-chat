from app.engine.memory.session_extractor import (
    compress_dialogue_timeline,
    compress_to_self_timeline,
)


def test_compress_keeps_short_timeline_intact():
    msgs = ["我偏好中文", "帮我查一下天气"]
    out = compress_to_self_timeline(msgs, max_chars=5000)
    assert "[1] 我偏好中文" in out
    assert "[2] 帮我查一下天气" in out


def test_compress_prefers_self_narrative_when_over_budget():
    noise = ["这个问题怎么回答？"] * 40
    owner = ["我偏好用数据可视化替代插图，不使用 AI 生成图。"]
    msgs = noise[:20] + owner + noise[20:]
    out = compress_to_self_timeline(msgs, max_chars=400)
    assert "自述时间线" in out or "数据可视化" in out or "对话时间线" in out
    assert "数据可视化" in out
    # 大量纯提问应被优先丢掉
    assert out.count("这个问题怎么回答") <= 2


def test_compress_dialogue_keeps_assistant_tail():
    """助手超长时保留文末（结论/排期常在最后），而非开头。"""
    turns = [
        ("user", "我偏好中文"),
        (
            "assistant",
            "开场铺垫很长。" + ("中间过程" * 40) + "最终：改为8周路线图，每周4-6小时。",
        ),
        ("user", "记住我喜欢简洁"),
    ]
    out = compress_dialogue_timeline(turns, max_chars=5000, assistant_max=40)
    assert "assistant:" in out
    assert "…" in out
    assert "8周" in out or "4-6" in out
    assert "开场铺垫" not in out
    assert "我偏好中文" in out


def test_compress_keeps_long_user_narrative_when_over_budget():
    long_pref = "我偏好" + ("用数据可视化替代插图并归档到知识库，" * 40)
    out = compress_dialogue_timeline(
        [("user", long_pref)],
        max_chars=200,
    )
    assert len(out) <= 200
    assert "我偏好" in out or "知识库" in out


def test_compress_nearby_assistant_only_immediate_next():
    turns = [
        ("user", "我偏好中文"),
        ("user", "我还偏好简洁"),
        ("assistant", "好的，已记录简洁偏好。"),
    ]
    out = compress_dialogue_timeline(turns, max_chars=120)
    # 压缩到自述+邻近助手时，第一条用户不应错挂第二条的助手（若触发邻近策略）
    # 全量仍短于预算时两者都在；收紧预算强制走邻近策略
    out2 = compress_dialogue_timeline(
        turns
        + [("user", "问题？" * 30), ("user", "另一个问题？" * 30)],
        max_chars=180,
    )
    assert "我还偏好简洁" in out2 or "我偏好中文" in out2


def test_compress_does_not_drop_all_users_for_assistant_only_preferred():
    """用户不像自述时，超预算也不得只剩助手时间线。"""
    turns = [
        ("user", "孩子高考是政史地。"),
        ("assistant", "了解，这是关于科目组合的说明。" + ("补充" * 40)),
        ("user", "然后总分怎么算？"),
        ("assistant", "我可以按规则解释。" + ("细节" * 40)),
    ]
    # 选一个介于「仅助手摘要」与「全文」之间的预算
    full = compress_dialogue_timeline(turns, max_chars=5000)
    assistants_only = "\n".join(
        line for line in full.splitlines() if "assistant:" in line
    )
    budget = max(len(assistants_only) + 20, 80)
    out = compress_dialogue_timeline(turns, max_chars=min(budget, len(full) - 1))
    assert any(x in out for x in ("孩子", "政史地", "总分"))
    assert "assistant:" in out or "孩子" in out


def test_pack_tiny_budget_keeps_at_least_one_user_line():
    out = compress_dialogue_timeline(
        [("user", "我偏好中文交流")],
        max_chars=10,
    )
    assert len(out) <= 10
    assert out.strip()
    assert "偏好" in out or "中文" in out or "…" in out


def test_pack_head_tail_keeps_middle_user_when_ends_are_assistants():
    """头尾皆助手、用户在中间时，压缩后仍须留下用户句。"""
    turns = [
        ("assistant", "开场。" + ("A" * 80)),
        ("user", "孩子高考是政史地。"),
        ("assistant", "结尾。" + ("B" * 80)),
    ]
    out = compress_dialogue_timeline(turns, max_chars=100, assistant_max=40)
    assert "政史地" in out or "孩子" in out
