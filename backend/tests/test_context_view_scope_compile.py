"""ViewScope 可见性、别名与 compile_search。"""

import pytest

from app.engine.channel_plugins.store import ChannelInstanceStore
from app.engine.context_view.compile import compile_search
from app.engine.context_view.errors import AmbiguousSubject, NotFound, OutOfScope
from app.engine.context_view.kb_kind import classify
from app.engine.context_view.scope import ViewScope
from app.engine.conversations import ConversationStore
from app.engine.memory.cards import KnowledgeCards, role_scope
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.roles import VISIBILITY_HIDDEN, RoleStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


@pytest.fixture
def ctx(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir(exist_ok=True)
    roles = RoleStore(tmp_path / "roles")
    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(kb, protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    owner = MemoryService(
        MemoryStore(tmp_path / "memory.db", owner_key="ws1"), repo, knowledge_writer=writer
    )
    channel_instances = ChannelInstanceStore(kb)
    cards = KnowledgeCards(
        tmp_path / "memory.db",
        owner=owner,
        roles=roles,
        conversations=conv,
        channel_instances=channel_instances,
    )
    return type(
        "Ctx",
        (),
        {
            "roles": roles,
            "conversations": conv,
            "cards": cards,
            "channel_instances": channel_instances,
        },
    )()


def _scope(ctx, *, cid=None, role_id=None):
    return ViewScope.build(
        conversations=ctx.conversations,
        roles=ctx.roles,
        cards=ctx.cards,
        channel_instances=ctx.channel_instances,
        conversation_id=cid,
        responding_role_id=role_id,
    )


def test_classify_kb_kinds():
    assert classify("a.md") == "doc"
    assert classify("run.sh") == "text"
    assert classify("pic.png") == "binary"


def test_tilde_resolves_responding_role(ctx):
    scope = _scope(ctx, role_id="default")
    uri = scope.resolve("lore://conversations/dm/~/")
    assert uri.owner == "default"


def test_unique_role_name_alias(ctx):
    rid = ctx.roles.create(name="档案员", system_prompt="")["id"]
    scope = _scope(ctx, role_id="default")
    uri = scope.resolve("lore://memory/role/档案员/")
    assert uri.subject == rid


def test_ambiguous_role_name(ctx):
    ctx.roles.create(name="同名", system_prompt="")
    ctx.roles.create(name="同名", system_prompt="")
    scope = _scope(ctx)
    with pytest.raises(AmbiguousSubject):
        scope.resolve("lore://memory/role/同名/")


def test_owner_turn_dm_visible_channel_not(ctx):
    role = ctx.roles.create(name="通道用", system_prompt="")
    persona = ctx.roles.create_persona(name="P", system_prompt="")
    inst = ctx.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    ch_cid = ctx.conversations.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    scope = _scope(ctx, cid=ctx.conversations.create(role_id="default"))
    with pytest.raises(OutOfScope):
        scope.resolve_and_check(f"lore://conversations/channels/{inst['id']}/{ch_cid}/")
    scope.resolve_and_check("lore://memory/role/default/")


def test_channel_turn_only_own_conversation(ctx):
    role = ctx.roles.create(name="通道用", system_prompt="")
    persona = ctx.roles.create_persona(name="API人设", system_prompt="")
    inst = ctx.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    other_cid = ctx.conversations.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    current = ctx.conversations.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    scope = _scope(ctx, cid=current, role_id=role["id"])
    assert scope.turn_kind == "channel"
    scope.resolve_and_check(
        f"lore://conversations/channels/{inst['id']}/{current}/"
    )
    with pytest.raises(OutOfScope):
        scope.resolve_and_check(
            f"lore://conversations/channels/{inst['id']}/{other_cid}/"
        )


def test_channel_persona_tilde(ctx):
    role = ctx.roles.create(name="通道用", system_prompt="")
    persona = ctx.roles.create_persona(name="API人设", system_prompt="")
    inst = ctx.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    cid = ctx.conversations.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    scope = _scope(ctx, cid=cid, role_id=role["id"])
    uri = scope.resolve("lore://memory/persona/~/")
    assert uri.subject == persona["id"]


def test_include_owner_memory_visibility(ctx):
    role = ctx.roles.create(name="通道用", system_prompt="")
    persona = ctx.roles.create_persona(name="P", system_prompt="")
    inst = ctx.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    cid = ctx.conversations.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    scope_off = _scope(ctx, cid=cid, role_id=role["id"])
    with pytest.raises(OutOfScope):
        scope_off.resolve_and_check("lore://memory/owner/")
    ctx.channel_instances.update(inst["id"], include_owner_memory=True)
    scope_on = _scope(ctx, cid=cid, role_id=role["id"])
    scope_on.resolve_and_check("lore://memory/owner/")


def test_mismatched_dm_owner_not_found(ctx):
    cid = ctx.conversations.create(role_id="default")
    scope = _scope(ctx)
    wrong_role = ctx.roles.create(name="其它", system_prompt="")["id"]
    with pytest.raises(NotFound):
        scope.resolve_and_check(f"lore://conversations/dm/{wrong_role}/{cid}/")


def test_compile_dedupe_and_memory_kind(ctx):
    scope = _scope(ctx, role_id="default")
    plan = compile_search(
        scope,
        [
            "lore://kb/",
            "lore://kb/技能/",
            "lore://memory/role/default/practice/",
        ],
    )
    assert plan.search_kb is True
    assert plan.kb_prefixes is None
    assert (role_scope("default"), "practice") in plan.memory_targets


def test_compile_explicit_current_conversation(ctx):
    cid = ctx.conversations.create(role_id="default")
    scope = _scope(ctx, cid=cid, role_id="default")
    plan = compile_search(scope, [f"lore://conversations/dm/default/{cid}/"])
    assert plan.include_current_conversation is True
    assert plan.search_conversations is True
    assert cid in plan.conversation_ids


def test_compile_default_paths_owner(ctx):
    scope = _scope(ctx, role_id="default")
    paths = scope.default_search_paths()
    assert "lore://kb/" in paths
    assert paths[1].endswith("/dm/default/")


def test_compile_kb_dir_and_file_prefixes(ctx, tmp_path):
    kb = tmp_path / "knowledge"
    (kb / "技能").mkdir(parents=True)
    (kb / "技能" / "a.md").write_text("x", encoding="utf-8")
    (kb / "笔记.md").write_text("y", encoding="utf-8")
    scope = _scope(ctx, role_id="default")
    plan = compile_search(
        scope,
        ["lore://kb/技能/", "lore://kb/笔记.md"],
    )
    assert plan.search_kb is True
    assert plan.kb_prefixes == ["技能/", "笔记.md"]


def test_compile_dm_role_zero_conversations_search_conversations_true(ctx):
    rid = ctx.roles.create(name="空角色", system_prompt="")["id"]
    scope = _scope(ctx, role_id="default")
    plan = compile_search(scope, [f"lore://conversations/dm/{rid}/"])
    assert plan.search_conversations is True
    assert plan.conversation_ids == []


def test_compile_tilde_dm_excludes_current_conversation(ctx):
    cid = ctx.conversations.create(role_id="default")
    other = ctx.conversations.create(role_id="default")
    scope = _scope(ctx, cid=cid, role_id="default")
    plan = compile_search(scope, ["lore://conversations/dm/~/"])
    assert plan.search_conversations is True
    assert cid not in plan.conversation_ids
    assert other in plan.conversation_ids
    assert plan.include_current_conversation is False


def test_hidden_api_role_excluded_from_dm_memory(ctx):
    persona = ctx.roles.create_persona(name="P", system_prompt="")
    role = ctx.roles.create(
        name="通道用",
        system_prompt="",
        visibility=VISIBILITY_HIDDEN,
        persona_id=persona["id"],
    )
    scope = _scope(ctx)
    roots = scope.visible_roots()
    dm_owners = {
        u.owner
        for u in roots
        if getattr(u, "bucket", None) == "dm" and u.owner
    }
    assert role["id"] not in dm_owners
