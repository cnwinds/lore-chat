from __future__ import annotations

from typing import Any

from app.config import EDITABLE_SETTING_KEYS, Settings, get_settings
from app.engine.document_synthesis import (
    build_archive_segment_messages,
    build_archive_transcript_messages,
    build_merge_archive_segments_messages,
    build_merge_documents_messages,
    build_reorganize_messages,
)
from app.engine.memory.card_consolidation import (
    CARD_PROFILE,
    CONSOLIDATION_MAX_INPUT,
    CONSOLIDATION_MAX_OPS,
    OWNER_PROFILE,
    build_consolidation_user_content,
)
from app.engine.memory.card_fade import CARD_FADE_DAYS
from app.engine.memory.cards import (
    CARD_MAINTENANCE_MIN_INTERVAL_HOURS,
    CONSOLIDATE_SCOPES_PER_TICK,
    EVOLVE_SCOPES_PER_TICK,
    MAX_CARDS_PER_SESSION,
)
from app.engine.memory.constants import ROOM_MAX_ROLE_LENSES, ROOM_WINDOW_MAX_MESSAGES
from app.engine.memory.persona_evolution import (
    EVOLUTION_MAX_CARDS,
    EVOLUTION_MAX_EDITS,
    EVOLUTION_MAX_PROPOSALS,
    EVOLUTION_MIN_CONVERSATIONS,
    _SYSTEM_PROMPT as PERSONA_EVOLVE_SYSTEM,
    sample_persona_evolution_user,
)
from app.engine.memory.role_card_extractor import (
    RoomDialogue,
    _SYSTEM_PROMPT as CARD_EXTRACT_SYSTEM,
    _build_room_user_content,
    _build_user_content,
    CardLens,
)
from app.engine.memory.session_extractor import (
    _SYSTEM_PROMPT,
    build_session_extract_user_content,
)
from app.engine.placement import PLACEMENT_DECIDE_SYSTEM, PLACEMENT_UNDERSTAND_SYSTEM
from app.engine.precepts_upgrade import (
    _RESOLVE_SYSTEM,
    build_precepts_resolve_user_content,
)
from app.models.candidate import format_vendor_model_label, resolve_provider_label
from app.models.effort import format_model_label

ALL_PURPOSE_KEYS: tuple[str, ...] = (
    "memory.owner_extract",
    "cards.extract",
    "memory.owner_consolidate",
    "cards.consolidate",
    "persona.evolve",
    "docs.archive",
    "docs.reorganize",
    "docs.merge",
    "docs.placement",
    "precepts.resolve",
    "index.embed",
)


def _pv(
    vid: str,
    label: str,
    system: str,
    user_template: str,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": vid,
        "label": label,
        "system": system,
        "user_template": user_template,
        "notes": notes or [],
    }


def _const(label: str, value: str | int, source: str) -> dict[str, Any]:
    return {"label": label, "value": value, "source": source}


def _node(**kwargs: Any) -> dict[str, Any]:
    base = {
        "trigger_kind": None,
        "chain": None,
        "temperature": None,
        "purpose": None,
        "conditions": [],
        "limits": [],
        "prompts": [],
        "guards": [],
        "outputs": [],
        "settings": [],
        "constants": [],
        "source_files": [],
        "links": [],
        "pause_key": None,
    }
    base.update(kwargs)
    return base


def build_nodes(settings: Settings) -> dict[str, dict[str, Any]]:
    idle_h = float(settings.memory_session_idle_hours or 24)
    maint_h = max(1.0, float(settings.memory_maintenance_interval_hours or 24))
    due_min = int(settings.group_assignment_due_minutes or 15)
    decay_stale = int(settings.memory_decay_stale_days or 90)
    window_max = ROOM_WINDOW_MAX_MESSAGES
    archive_whole_msgs = build_archive_transcript_messages(
        "（示例会话记录）", "{《戒律》与会话总结规约}"
    )
    archive_whole_sys = archive_whole_msgs[0]["content"]
    archive_whole_user = archive_whole_msgs[1]["content"]
    archive_seg_msgs = build_archive_segment_messages(
        "（片段正文）",
        "{《戒律》规约}",
        {"first_message_id": "m1", "last_message_id": "m9"},
    )
    archive_seg_sys = archive_seg_msgs[0]["content"]
    archive_seg_user = archive_seg_msgs[1]["content"]
    merge_seg_msgs = build_merge_archive_segments_messages(
        ["段摘要一", "段摘要二"], "{规约}"
    )
    merge_seg_sys = merge_seg_msgs[0]["content"]
    merge_seg_user = merge_seg_msgs[1]["content"]
    reorganize_sys, reorganize_user = build_reorganize_messages(
        "（已有正文）", "（新内容）", "示例标题"
    )
    merge_doc_sys, merge_doc_user = build_merge_documents_messages(
        [("路径/a.md", "正文 A")], "合并要求示例"
    )
    understand_sys = PLACEMENT_UNDERSTAND_SYSTEM
    decide_sys = PLACEMENT_DECIDE_SYSTEM

    card_user = _build_user_content(
        lens=CardLens(
            scope="role:示例",
            origin="direct",
            subject_name="{角色名}",
            persona_text="{角色设定节选，≤800 字}",
        ),
        existing_cards=[{"slot_key": "槽位键", "statement": "{卡片正文}"}],
        owner_summary=["{已确认画像条目}"],
        dialogue_body="{对话时间线：按预算保留头尾}",
    )
    room_user = _build_room_user_content(
        lens=CardLens(
            scope="role:示例",
            origin="direct",
            subject_name="{角色名}",
            persona_text="{角色设定节选，≤800 字}",
        ),
        room=RoomDialogue(
            kind="group",
            title="{群聊标题}",
            peer_names=["{同伴名}"],
            context=[("{发言者}", "{上下文一句}")],
            lines=[("{发言者}", "{本轮一句}")],
        ),
        existing_cards=[],
        owner_summary=[],
    )
    session_user = build_session_extract_user_content(
        [{"slot_key": "槽位键", "statement": "{已确认画像条目}"}],
        "{对话时间线：按预算保留头尾}",
    )
    owner_consolidate_user = build_consolidation_user_content(
        owner=True,
        lens=None,
        fact_lines=["- [槽位键] {记忆正文}"],
    )
    card_consolidate_user = build_consolidation_user_content(
        owner=False,
        lens=CardLens(
            scope="role:示例",
            origin="direct",
            subject_name="{角色名}",
            persona_text="{角色设定节选，≤800 字}",
        ),
        fact_lines=["- [槽位键] {卡片正文}"],
    )
    precepts_user = build_precepts_resolve_user_content(
        {"marked": "{《戒律》全文，运行时注入}"},
        conflict_block="{冲突块对照，运行时注入}",
    )

    nodes: dict[str, dict[str, Any]] = {}

    nodes["trigger.session_idle"] = _node(
        id="trigger.session_idle",
        type="trigger",
        title="会话空闲",
        subtitle="定时检查",
        trigger_kind="schedule",
        description=(
            f"派生线程持续检查：若会话已标待观察且距最后一条主人消息空闲满 "
            f"{idle_h:g} 小时仍无新消息，则进入记忆抽取队列。"
        ),
        settings=["memory_session_idle_hours"],
        source_files=["app/engine/memory/session_observe.py", "app/main.py"],
    )

    nodes["trigger.session_immediate"] = _node(
        id="trigger.session_immediate",
        type="trigger",
        title="即时定稿",
        subtitle="事件触发",
        trigger_kind="event",
        description=(
            f"话题换段关段、会话归档落库，或互通/群聊相对游标累计满 "
            f"{window_max} 条新消息时，跳过空闲等待直接入队抽取。"
        ),
        limits=[f"群聊窗口增量上限 {window_max} 条"],
        source_files=["app/engine/memory/session_observe.py", "app/engine/conversations.py"],
    )

    nodes["code.lens_dispatch"] = _node(
        id="code.lens_dispatch",
        type="code",
        title="按会话分派",
        subtitle="私聊、通道、群聊各有抽取对象",
        description=(
            "按会话类型决定为谁抽取：私聊抽主人与本角色；通道只抽共用角色且来源为外部；"
            "互通/群聊在主人发过言时为每个发过言的左栏角色各抽一次卡片。"
        ),
        conditions=["无主人发言时不抽主人记忆"],
        limits=[f"互通/群聊每次最多为 {ROOM_MAX_ROLE_LENSES} 个角色抽卡"],
        source_files=["app/engine/memory/cards.py", "app/engine/memory/session_observe.py"],
    )

    nodes["memory.owner_extract"] = _node(
        id="memory.owner_extract",
        type="llm",
        title="主人记忆抽取",
        subtitle="辅助链 · T=0.1 · ≤8 条",
        description="通读定稿对话，提取关于主人的稳定画像，产出槽位动作列表。",
        conditions=[
            "用户句含密钥则跳过该句；全无有效用户句则不调用",
            "须通过对主人第一人称表面归属等门槛后才落库",
        ],
        limits=["单次最多 8 条"],
        chain="utility",
        temperature=0.1,
        purpose="memory.owner_extract",
        pause_key="session_observe",
        prompts=[
            _pv(
                "default",
                "默认定稿",
                _SYSTEM_PROMPT,
                session_user,
            )
        ],
        guards=[
            "含密钥的结果直接丢弃",
            "没有「我 / 我家」这类主人指称的句子不落库",
            "同一槽位合并、删过的不复活、敏感内容不自动保存",
        ],
        outputs=["主人记忆候选/确认", "成长日志", "前端记忆刷新通知"],
        settings=["memory_session_idle_hours"],
        constants=[_const("单次上限", 8, "session_extractor._MAX_ITEMS")],
        source_files=["app/engine/memory/session_extractor.py"],
    )

    nodes["cards.extract"] = _node(
        id="cards.extract",
        type="llm",
        title="角色知识卡抽取",
        subtitle="辅助链 · T=0.1 · ≤6 张",
        description="从对话提炼本角色下次仍用得上的认知，写成知识卡。",
        conditions=[
            "外部通道只许领域知识与受众认知两类",
            "同伴断言不算依据，只有工具取证结果可作依据",
            "无有效主人/本角色发言时不调用",
        ],
        limits=[f"单次最多 {MAX_CARDS_PER_SESSION} 张"],
        chain="utility",
        temperature=0.1,
        purpose="cards.extract",
        pause_key="session_observe",
        prompts=[
            _pv("dm", "私聊与通道", CARD_EXTRACT_SYSTEM, card_user),
            _pv(
                "room",
                "群聊与互通",
                CARD_EXTRACT_SYSTEM,
                room_user,
                ["互通/群聊走群聊抽取路径"],
            ),
        ],
        guards=[
            "含密钥的结果直接丢弃",
            "外部来源只允许领域与受众两类卡片",
            "同一槽位合并、删过的不复活、敏感内容不自动保存",
        ],
        outputs=["角色知识卡", "前端卡片刷新通知"],
        settings=["memory_session_idle_hours"],
        constants=[
            _const("单次上限", MAX_CARDS_PER_SESSION, "cards.MAX_CARDS_PER_SESSION")
        ],
        source_files=["app/engine/memory/role_card_extractor.py"],
    )

    nodes["code.card_fade"] = _node(
        id="code.card_fade",
        type="code",
        title="卡片淡出",
        subtitle=f"{CARD_FADE_DAYS} 天无新出处 → 已淡出",
        description="长期无新出处的卡片先进入已淡出，待印证再久则作废；主人亲手改过的卡片豁免。",
        limits=[f"每作用域维护间隔 ≥ {CARD_MAINTENANCE_MIN_INTERVAL_HOURS} 小时"],
        settings=[],
        source_files=["app/engine/memory/card_fade.py", "app/engine/memory/cards.py"],
    )

    nodes["memory.owner_consolidate"] = _node(
        id="memory.owner_consolidate",
        type="llm",
        title="主人记忆整理",
        subtitle="辅助链 · T=0.1",
        description="合并/抽象/补条件/取代主人记忆，只重组已有条目。",
        conditions=[
            f"至少 2 条活跃记忆且距上次整理已过 {CARD_MAINTENANCE_MIN_INTERVAL_HOURS}h",
            "主人亲定与「要求记住」条目只读",
            "暂停整理时不跑整理且不刷新上次整理时间",
        ],
        limits=[
            f"输入最多 {CONSOLIDATION_MAX_INPUT} 条",
            f"每轮维护最多 {CONSOLIDATE_SCOPES_PER_TICK} 个作用域（含主人）",
        ],
        chain="utility",
        temperature=0.1,
        purpose="memory.owner_consolidate",
        pause_key="consolidation",
        prompts=[
            _pv(
                "default",
                "主人记忆",
                OWNER_PROFILE.system_prompt,
                owner_consolidate_user,
            )
        ],
        guards=[
            "只读来源不会被改写",
            "种类只能来自参与条目本身",
            "整理后主语仍须是主人",
            "敏感内容不自动保存",
        ],
        outputs=["合并后的主人记忆", "整理成长日志"],
        settings=[],
        constants=[
            _const("输入上限", CONSOLIDATION_MAX_INPUT, "card_consolidation.CONSOLIDATION_MAX_INPUT"),
            _const("单次整理动作上限", CONSOLIDATION_MAX_OPS, "card_consolidation.CONSOLIDATION_MAX_OPS"),
        ],
        source_files=["app/engine/memory/card_consolidation.py"],
    )

    nodes["cards.consolidate"] = _node(
        id="cards.consolidate",
        type="llm",
        title="角色卡整理",
        subtitle="辅助链 · T=0.1",
        description="对某角色作用域的知识卡做合并、抽象、补条件或取代。",
        conditions=["至少 2 张卡", "来源不混：外部不得取代主人来源"],
        limits=[f"每轮 ≤ {CONSOLIDATE_SCOPES_PER_TICK} 作用域"],
        chain="utility",
        temperature=0.1,
        purpose="cards.consolidate",
        pause_key="consolidation",
        prompts=[
            _pv(
                "default",
                "角色卡",
                CARD_PROFILE.system_prompt,
                card_consolidate_user,
            )
        ],
        guards=["手改卡片只读", "外部来源不能取代主人来源", "取代时不合并出处"],
        outputs=["精炼后的角色卡"],
        source_files=["app/engine/memory/card_consolidation.py"],
    )

    nodes["persona.evolve"] = _node(
        id="persona.evolve",
        type="llm",
        title="人设进化",
        subtitle="对话链 · T=0.1",
        description="把反复印证且未审过的主人来源卡压进人设，或提议升格 Skill/文档。",
        conditions=[
            f"卡须跨 ≥ {EVOLUTION_MIN_CONVERSATIONS} 段会话或主人手改过",
            "角色初次设定进行中时跳过",
            "多角色共用人设时不提议升格",
            "暂停人设进化时不跑进化",
        ],
        limits=[
            f"每轮 ≤ {EVOLVE_SCOPES_PER_TICK} 作用域",
            f"最多 {EVOLUTION_MAX_EDITS} 条人设改动、{EVOLUTION_MAX_PROPOSALS} 条升格提议",
        ],
        chain="chat",
        temperature=0.1,
        purpose="persona.evolve",
        pause_key="persona_evolution",
        prompts=[
            _pv(
                "default",
                "人设维护",
                PERSONA_EVOLVE_SYSTEM,
                sample_persona_evolution_user(),
                ["【全局规则】运行时注入《戒律》全文"],
            )
        ],
        guards=[
            "改动须能对应到送审列表里的卡或记忆编号",
            "主人手改保护区与回退墓碑",
            "写入前核对人设没被同时改过，改过就放弃这次",
        ],
        outputs=["人设修订", "升格提议"],
        constants=[
            _const("送审卡上限", EVOLUTION_MAX_CARDS, "persona_evolution.EVOLUTION_MAX_CARDS"),
        ],
        source_files=[
            "app/engine/memory/persona_evolution.py",
            "app/engine/persona_edits.py",
        ],
    )

    nodes["code.memory_decay"] = _node(
        id="code.memory_decay",
        type="code",
        title="记忆衰减",
        subtitle=f"目标或项目 {decay_stale} 天未提及 → 过期",
        description="按种类与天数把目标、项目类过期，推断项降为待印证或作废。",
        conditions=["身份类、亲定与「要求记住」条目豁免"],
        limits=["间隔由「记忆衰减检查间隔」设定控制"],
        settings=[
            "memory_maintenance_interval_hours",
            "memory_decay_stale_days",
            "memory_decay_inferred_days",
            "memory_decay_candidate_days",
        ],
        source_files=["app/engine/memory_maintenance.py", "app/engine/memory/decay.py"],
    )

    nodes["code.fts"] = _node(
        id="code.fts",
        type="code",
        title="全文索引同步",
        subtitle="新内容入队后由派生线程同步",
        description="新消息或文档写入后入队，派生线程同步全文检索索引。",
        limits=["派生线程约每 0.5 秒一批，每批最多 20 条"],
        source_files=["app/engine/derivation_worker.py"],
    )

    nodes["index.embed"] = _node(
        id="index.embed",
        type="embed",
        title="向量补全",
        subtitle="嵌入链",
        description="为待补向量块调用嵌入模型，新内容优先，失败退避。",
        limits=["每轮最多 32 块", "无嵌入链配置时跳过"],
        chain="embed",
        purpose="index.embed",
        outputs=["分区向量索引"],
        source_files=["app/index/partitioned/search_index.py", "app/main.py"],
    )

    nodes["store.search_index"] = _node(
        id="store.search_index",
        type="store",
        title="检索索引",
        subtitle="写入",
        description="分区 FTS + 向量投影，供文档/会话/卡片检索。",
        outputs=["分区全文与向量索引"],
        source_files=["app/index/partitioned/"],
    )

    nodes["store.owner_memory"] = _node(
        id="store.owner_memory",
        type="store",
        title="主人记忆库",
        subtitle="长期画像",
        description="经记忆服务写入的稳定主人画像。",
        source_files=["app/engine/memory/store.py", "app/engine/memory/service.py"],
    )

    nodes["store.role_cards"] = _node(
        id="store.role_cards",
        type="store",
        title="角色知识卡",
        subtitle="按角色保存",
        description="按角色与人设作用域存储，带成长日志与整理状态。",
        source_files=["app/engine/memory/cards.py"],
    )

    nodes["store.persona"] = _node(
        id="store.persona",
        type="store",
        title="角色人设",
        subtitle="角色设定",
        description="人设进化写入的修订，可回退。",
        source_files=["app/engine/roles.py", "app/engine/memory/persona_history.py"],
    )

    nodes["store.proposals"] = _node(
        id="store.proposals",
        type="store",
        title="升格提议",
        subtitle="待主人确认",
        description="Skill/文档升格提议，接受后由主人发送触发。",
        source_files=["app/engine/memory/card_persona_state.py"],
    )

    nodes["trigger.card_schedule"] = _node(
        id="trigger.card_schedule",
        type="trigger",
        title="定时维护",
        trigger_kind="schedule",
        subtitle="每小时",
        description="卡片维护线程按固定间隔检查各作用域，到期则依次淡出、整理与人设进化。",
        limits=[f"每作用域 ≥ {CARD_MAINTENANCE_MIN_INTERVAL_HOURS}h 至多一次"],
        source_files=["app/main.py", "app/engine/memory/cards.py"],
    )

    nodes["trigger.memory_decay_schedule"] = _node(
        id="trigger.memory_decay_schedule",
        type="trigger",
        title="衰减检查",
        trigger_kind="schedule",
        subtitle=f"每 {maint_h:g} 小时",
        description=f"记忆衰减线程每 {maint_h:g} 小时运行一次过期与降级任务。",
        settings=["memory_maintenance_interval_hours"],
        source_files=["app/main.py", "app/engine/memory_maintenance.py"],
    )

    nodes["trigger.index_enqueue"] = _node(
        id="trigger.index_enqueue",
        type="trigger",
        title="内容写入",
        trigger_kind="event",
        subtitle="消息/文档",
        description="新消息或知识库写入后入队全文索引，随后派生线程同步。",
        source_files=["app/engine/conversations.py", "app/engine/derivation_worker.py"],
    )

    nodes["turn.agent"] = _node(
        id="turn.agent",
        type="turn",
        title="主对话回合",
        subtitle="对话链 + 工具",
        description="定时任务、群派工超时、互通唤醒等走 Agent 主提示词，不在此 catalog 展开。",
        trigger_kind="schedule",
        chain="chat",
        source_files=["app/engine/agent/", "app/engine/chat/"],
    )

    nodes["docs.archive"] = _node(
        id="docs.archive",
        type="llm",
        title="会话归档成文",
        subtitle="对话链",
        description="把会话记录整理成知识库文档；过长则分段摘要再合并。",
        conditions=["超过「归档分段阈值」则分段"],
        chain="chat",
        temperature=0.2,
        purpose="docs.archive",
        prompts=[
            _pv("whole", "整段归档", archive_whole_sys, archive_whole_user),
            _pv(
                "segment",
                "分段摘要",
                archive_seg_sys,
                archive_seg_user,
                ["超过「归档分段阈值」时分段"],
            ),
            _pv(
                "merge_segments",
                "段摘要合并",
                merge_seg_sys,
                merge_seg_user,
            ),
        ],
        outputs=["知识库文档"],
        settings=["summarize_segment_chars"],
        links=[{"lane": "session_observe", "label": "落库后立即抽取"}],
        source_files=["app/engine/document_synthesis.py", "app/engine/conversation_archive.py"],
    )

    nodes["docs.reorganize"] = _node(
        id="docs.reorganize",
        type="llm",
        title="写入合并",
        subtitle="对话链",
        description="写入文档工具合并到已有文档时重组正文。",
        chain="chat",
        temperature=0.2,
        purpose="docs.reorganize",
        prompts=[_pv("default", "合并重组", reorganize_sys, reorganize_user)],
        outputs=["更新后的知识库文档"],
        source_files=["app/engine/document_synthesis.py", "app/engine/knowledge_writer.py"],
    )

    nodes["docs.merge"] = _node(
        id="docs.merge",
        type="llm",
        title="多文档合并",
        subtitle="对话链",
        description="界面或工作流发起多源合并成一篇。",
        chain="chat",
        temperature=0.2,
        purpose="docs.merge",
        prompts=[_pv("default", "合并成文", merge_doc_sys, merge_doc_user)],
        outputs=["合并稿（审阅）"],
        source_files=["app/engine/document_synthesis.py", "app/engine/merge_workflow.py"],
    )

    nodes["docs.placement"] = _node(
        id="docs.placement",
        type="llm",
        title="归位决策",
        subtitle="辅助链 · 概括主题并决定存放位置",
        description="合并审阅接受前，理解主题并决定新建或并入已有文档。",
        chain="utility",
        temperature=0.2,
        purpose="docs.placement",
        prompts=[
            _pv(
                "understand",
                "一句话摘要",
                understand_sys,
                "{待归位正文，运行时注入}",
            ),
            _pv(
                "decide",
                "归位决策",
                decide_sys,
                "{摘要与相关文档列表，运行时注入}",
            ),
        ],
        outputs=["归位决策结果"],
        source_files=["app/engine/placement.py"],
    )

    nodes["precepts.resolve"] = _node(
        id="precepts.resolve",
        type="llm",
        title="戒律冲突合并",
        subtitle="辅助链 · T=0",
        description="官方稿与本地稿三路合并有冲突时，模型只填冲突块产出待确认稿。",
        chain="utility",
        temperature=0.0,
        purpose="precepts.resolve",
        prompts=[
            _pv(
                "default",
                "冲突块合并",
                _RESOLVE_SYSTEM,
                precepts_user,
            )
        ],
        guards=["仍含冲突标记的正文不会保存", "仅待确认稿写入暂存"],
        outputs=["待确认合并稿"],
        source_files=["app/engine/precepts_upgrade.py"],
    )

    nodes["store.kb_docs"] = _node(
        id="store.kb_docs",
        type="store",
        title="知识库文档",
        subtitle="版本库与索引",
        description="归档、合并、写入文档工具的最终落点。",
        source_files=["app/engine/knowledge_writer.py"],
    )

    nodes["store.merge_review"] = _node(
        id="store.merge_review",
        type="store",
        title="合并审阅",
        subtitle="待主人审阅的合并稿",
        description="多文档合并的审阅会话，接受后落库。",
        source_files=["app/engine/merge_workflow.py"],
    )

    nodes["store.precepts_pending"] = _node(
        id="store.precepts_pending",
        type="store",
        title="戒律待确认",
        subtitle="待主人确认",
        description="冲突合并结果暂存，确认后才写活《戒律》。",
        source_files=["app/engine/precepts_upgrade.py"],
    )

    nodes["store.conversation"] = _node(
        id="store.conversation",
        type="store",
        title="会话消息",
        subtitle="写入会话",
        description="对话记录与派生任务队列。",
        links=[{"lane": "session_observe", "label": "新消息随后参与记忆抽取"}],
        source_files=["app/engine/conversations.py"],
    )

    nodes["trigger.role_schedule"] = _node(
        id="trigger.role_schedule",
        type="trigger",
        title="角色定时任务",
        subtitle="每 30 秒",
        trigger_kind="schedule",
        description="后台每 30 秒检查到期的角色定时任务，在主对话里发起一条回合。",
        source_files=["app/engine/role_schedule_worker.py", "app/main.py"],
    )

    nodes["trigger.group_due"] = _node(
        id="trigger.group_due",
        type="trigger",
        title="群派工超时",
        subtitle="事件",
        trigger_kind="event",
        description=(
            f"群聊里派工给协调者后，超过 {due_min} 分钟仍未回执时唤醒协调者处理。"
        ),
        settings=["group_assignment_due_minutes"],
        source_files=["app/engine/rooms/delivery.py"],
    )

    nodes["trigger.peer_inbound"] = _node(
        id="trigger.peer_inbound",
        type="trigger",
        title="互通与群聊投递",
        subtitle="事件",
        trigger_kind="event",
        description="互通或群聊有新消息投递给某角色时，唤醒该角色发起对话回合。",
        source_files=["app/engine/rooms/", "app/engine/role_schedule_worker.py"],
    )

    nodes["trigger.tool_summarize"] = _node(
        id="trigger.tool_summarize",
        type="trigger",
        title="归档工具",
        subtitle="手动",
        trigger_kind="manual",
        description="主对话里调用会话归档工具时触发。",
        source_files=["app/engine/conversation_archive.py"],
    )

    nodes["trigger.tool_write_doc"] = _node(
        id="trigger.tool_write_doc",
        type="trigger",
        title="写入已有文档",
        subtitle="手动",
        trigger_kind="manual",
        description="主对话写入已有知识库文档且选择合并写入方式时触发。",
        source_files=["app/engine/knowledge_writer.py"],
    )

    nodes["trigger.ui_merge"] = _node(
        id="trigger.ui_merge",
        type="trigger",
        title="界面合并",
        subtitle="手动",
        trigger_kind="manual",
        description="在界面发起多文档合并或重新生成合并稿时触发。",
        source_files=["app/engine/merge_workflow.py"],
    )

    nodes["trigger.precepts_propose"] = _node(
        id="trigger.precepts_propose",
        type="trigger",
        title="戒律更新请求",
        subtitle="手动",
        trigger_kind="manual",
        description="在「戒律更新」里请求生成 AI 合并稿时触发。",
        source_files=["app/engine/precepts_upgrade.py"],
    )

    return nodes


def build_lanes(settings: Settings) -> list[dict[str, Any]]:
    idle_h = float(settings.memory_session_idle_hours or 24)
    maint_h = max(1.0, float(settings.memory_maintenance_interval_hours or 24))
    due_min = int(settings.group_assignment_due_minutes or 15)
    window_max = ROOM_WINDOW_MAX_MESSAGES
    return [
        {
            "id": "session_observe",
            "group": "auto",
            "title": "会话定稿观察",
            "summary": "空闲或事件触发后抽取主人记忆与角色卡",
            "cadence": (
                f"会话空闲 {idle_h:g} 小时后抽取；换段、归档或群聊累计 "
                f"{window_max} 条时立即抽取"
            ),
            "worker": "derivation-worker",
            "pause_key": "session_observe",
            "steps": [
                {
                    "kind": "trigger",
                    "label": None,
                    "nodes": ["trigger.session_idle", "trigger.session_immediate"],
                },
                {
                    "kind": "stage",
                    "label": "分派",
                    "nodes": ["code.lens_dispatch"],
                },
                {
                    "kind": "stage",
                    "label": "模型抽取",
                    "nodes": ["memory.owner_extract", "cards.extract"],
                },
                {
                    "kind": "output",
                    "label": None,
                    "nodes": ["store.owner_memory", "store.role_cards"],
                },
            ],
        },
        {
            "id": "card_maintenance",
            "group": "auto",
            "title": "卡片维护",
            "summary": "淡出、整理、人设进化与卡片索引对账",
            "cadence": (
                f"每小时检查一次，每个角色每天最多整理、进化一次"
            ),
            "worker": "card-maintenance",
            "pause_key": None,
            "steps": [
                {"kind": "trigger", "label": None, "nodes": ["trigger.card_schedule"]},
                {"kind": "stage", "label": "淡出", "nodes": ["code.card_fade"]},
                {
                    "kind": "stage",
                    "label": "整理",
                    "nodes": ["memory.owner_consolidate", "cards.consolidate"],
                },
                {"kind": "stage", "label": "进化", "nodes": ["persona.evolve"]},
                {
                    "kind": "output",
                    "label": None,
                    "nodes": [
                        "store.owner_memory",
                        "store.role_cards",
                        "store.persona",
                        "store.proposals",
                        "store.search_index",
                    ],
                },
            ],
        },
        {
            "id": "memory_decay",
            "group": "auto",
            "title": "主人记忆衰减",
            "summary": "按天数降级或作废非身份类记忆",
            "cadence": f"每 {maint_h:g} 小时一次",
            "worker": "memory-maintenance",
            "pause_key": None,
            "steps": [
                {
                    "kind": "trigger",
                    "label": None,
                    "nodes": ["trigger.memory_decay_schedule"],
                },
                {"kind": "stage", "label": None, "nodes": ["code.memory_decay"]},
                {"kind": "output", "label": None, "nodes": ["store.owner_memory"]},
            ],
        },
        {
            "id": "index_derivation",
            "group": "auto",
            "title": "索引派生",
            "summary": "全文同步与向量补全",
            "cadence": "新消息、文档写入后几秒内",
            "worker": "derivation-worker",
            "pause_key": None,
            "steps": [
                {"kind": "trigger", "label": None, "nodes": ["trigger.index_enqueue"]},
                {"kind": "stage", "label": "全文", "nodes": ["code.fts"]},
                {"kind": "stage", "label": "向量", "nodes": ["index.embed"]},
                {"kind": "output", "label": None, "nodes": ["store.search_index"]},
            ],
        },
        {
            "id": "auto_turns",
            "group": "auto_turn",
            "title": "自动发起的对话",
            "summary": "走主对话 Agent，非后台提示词",
            "cadence": f"定时任务到期、派工超过 {due_min} 分钟未回执或角色互通时",
            "worker": "role-schedule-worker",
            "pause_key": None,
            "steps": [
                {
                    "kind": "trigger",
                    "label": None,
                    "nodes": [
                        "trigger.role_schedule",
                        "trigger.group_due",
                        "trigger.peer_inbound",
                    ],
                },
                {"kind": "stage", "label": None, "nodes": ["turn.agent"]},
                {
                    "kind": "output",
                    "label": None,
                    "nodes": ["store.conversation"],
                },
            ],
        },
        {
            "id": "ondemand_archive",
            "group": "on_demand",
            "title": "会话归档",
            "summary": "把长对话整理成知识库文档",
            "cadence": "主对话调用归档工具时",
            "worker": None,
            "pause_key": None,
            "steps": [
                {"kind": "trigger", "label": None, "nodes": ["trigger.tool_summarize"]},
                {"kind": "stage", "label": None, "nodes": ["docs.archive"]},
                {"kind": "output", "label": None, "nodes": ["store.kb_docs"]},
            ],
        },
        {
            "id": "ondemand_write_merge",
            "group": "on_demand",
            "title": "写入合并",
            "summary": "新内容与已有文档合并成一篇",
            "cadence": "写入已有文档且选择合并方式时",
            "worker": None,
            "pause_key": None,
            "steps": [
                {"kind": "trigger", "label": None, "nodes": ["trigger.tool_write_doc"]},
                {"kind": "stage", "label": None, "nodes": ["docs.reorganize"]},
                {"kind": "output", "label": None, "nodes": ["store.kb_docs"]},
            ],
        },
        {
            "id": "ondemand_doc_merge",
            "group": "on_demand",
            "title": "多文档合并",
            "summary": "把多篇文档合成一篇并决定放在哪",
            "cadence": "界面发起多文档合并或重新生成时",
            "worker": None,
            "pause_key": None,
            "steps": [
                {"kind": "trigger", "label": None, "nodes": ["trigger.ui_merge"]},
                {"kind": "stage", "label": "成文", "nodes": ["docs.merge"]},
                {"kind": "stage", "label": "归位", "nodes": ["docs.placement"]},
                {
                    "kind": "output",
                    "label": None,
                    "nodes": ["store.merge_review", "store.kb_docs"],
                },
            ],
        },
        {
            "id": "ondemand_precepts",
            "group": "on_demand",
            "title": "戒律冲突合并",
            "summary": "戒律模板更新与本地改动冲突时，生成合并稿给主人确认",
            "cadence": "打开「戒律更新」请求 AI 合并稿时",
            "worker": None,
            "pause_key": None,
            "steps": [
                {"kind": "trigger", "label": None, "nodes": ["trigger.precepts_propose"]},
                {"kind": "stage", "label": None, "nodes": ["precepts.resolve"]},
                {"kind": "output", "label": None, "nodes": ["store.precepts_pending"]},
            ],
        },
    ]


def build_catalog_static(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    nodes = build_nodes(settings)
    lanes = build_lanes(settings)
    return {
        "groups": [
            {
                "id": "auto",
                "title": "自动",
                "hint": "后台线程定时运行，或在对话事件后立即运行",
            },
            {
                "id": "auto_turn",
                "title": "自动发起的对话回合",
                "hint": "仍走主对话提示词，完成后可能进入会话观察",
            },
            {
                "id": "on_demand",
                "title": "按需",
                "hint": "工具或界面操作触发",
            },
        ],
        "lanes": lanes,
        "nodes": nodes,
        "pausable": [
            {
                "key": "session_observe",
                "label": "会话记忆抽取",
                "hint": "暂停期间待抽取的会话会累积，恢复后补跑",
            },
            {
                "key": "consolidation",
                "label": "整理",
                "hint": "暂停整理时不合并主人记忆与角色卡；卡片淡出照常",
            },
            {
                "key": "persona_evolution",
                "label": "人设进化",
                "hint": "暂停后人设不再自动改写，淡出与整理照常",
            },
        ],
    }


def setting_meta(settings: Settings) -> dict[str, dict[str, Any]]:
    def num(
        key: str,
        label: str,
        *,
        unit: str | None,
        hint: str,
        min_v: float | None = None,
        max_v: float | None = None,
        step: float | None = None,
    ) -> dict[str, Any]:
        val = getattr(settings, key)
        return {
            "key": key,
            "label": label,
            "kind": "number",
            "value": float(val),
            "unit": unit,
            "min": min_v,
            "max": max_v,
            "step": step,
            "hint": hint,
        }

    meta = {
        "memory_session_idle_hours": num(
            "memory_session_idle_hours",
            "会话抽取空闲时长",
            unit="小时",
            hint="最后一条主人消息后需空闲多久才抽取",
            min_v=0.5,
            max_v=168,
            step=0.5,
        ),
        "memory_maintenance_interval_hours": num(
            "memory_maintenance_interval_hours",
            "记忆衰减检查间隔",
            unit="小时",
            hint="多久检查一次记忆是否该降级或过期",
            min_v=1,
            max_v=168,
            step=1,
        ),
        "memory_decay_stale_days": num(
            "memory_decay_stale_days",
            "目标/项目过期天数",
            unit="天",
            hint="确认后长期无新出处则过期",
            min_v=7,
            max_v=3650,
            step=1,
        ),
        "memory_decay_inferred_days": num(
            "memory_decay_inferred_days",
            "推断项降级天数",
            unit="天",
            hint="推断出的偏好、工作方式多久无印证就降为待印证",
            min_v=7,
            max_v=3650,
            step=1,
        ),
        "memory_decay_candidate_days": num(
            "memory_decay_candidate_days",
            "待印证作废天数",
            unit="天",
            hint="待印证长期无支撑则作废",
            min_v=7,
            max_v=3650,
            step=1,
        ),
        "summarize_segment_chars": num(
            "summarize_segment_chars",
            "归档分段阈值",
            unit="字",
            hint="会话归档超过该字数则分段处理",
            min_v=4000,
            max_v=200000,
            step=1000,
        ),
        "group_assignment_due_minutes": num(
            "group_assignment_due_minutes",
            "群派工超时",
            unit="分钟",
            hint="工人开回合后未回执则叫醒协调者",
            min_v=1,
            max_v=1440,
            step=1,
        ),
    }
    for key in meta:
        assert key in EDITABLE_SETTING_KEYS, key
    return meta


def model_chain_rows(settings: Settings, chain: str) -> list[dict[str, str]]:
    from app.models.candidate import resolve_chain_candidates

    rows: list[dict[str, str]] = []
    for cand in resolve_chain_candidates(settings, chain):  # type: ignore[arg-type]
        base = format_model_label(
            cand.model,
            thinking=bool(cand.thinking),
            effort=str(cand.effort or ""),
            effort_options=tuple(cand.effort_options or ()),
        )
        vendor = resolve_provider_label(
            getattr(cand, "provider", None),
            getattr(cand, "provider_label", None),
        )
        rows.append(
            {
                "label": format_vendor_model_label(vendor, base),
                "model": cand.model,
            }
        )
    return rows


def chain_summaries(settings: Settings) -> dict[str, dict[str, Any]]:
    return {
        "utility": {
            "chain": "utility",
            "label": "辅助链",
            "models": model_chain_rows(settings, "utility"),
        },
        "chat": {
            "chain": "chat",
            "label": "对话链",
            "models": model_chain_rows(settings, "chat"),
        },
        "embed": {
            "chain": "embed",
            "label": "嵌入链",
            "models": model_chain_rows(settings, "embed"),
        },
    }
