from app.engine.agent.prompts import MODE_DEFAULT
from app.engine.agent.tool_catalog import select_tools
from app.engine.conversation.transcript import ConversationTranscript
from app.engine.conversations import ConversationStore
from app.engine.rooms.delivery import RoomDelivery
from app.engine.rooms.schema import KIND_OWNER_DM, KIND_PEER_DM, ROOM_ROLE_PLACEHOLDER
from app.engine.rooms.types import format_peer_message
from app.engine.roles import DEFAULT_ROLE_ID, RoleStore


def _conv(tmp_path):
    return ConversationStore(tmp_path / "conversations")


def _roles(tmp_path):
    return RoleStore(tmp_path / "roles")


def test_create_backfills_owner_dm_participants(tmp_path):
    store = _conv(tmp_path)
    cid = store.create()
    assert store.rooms.conversation_kind(cid) == KIND_OWNER_DM
    assert DEFAULT_ROLE_ID in store.rooms.list_role_participants(cid)


def test_find_or_create_peer_dm_unique(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="游戏开发助手", system_prompt="做游戏")
    a = DEFAULT_ROLE_ID
    b = other["id"]
    r1 = store.rooms.find_or_create_peer_dm(a, b, title="协作")
    r2 = store.rooms.find_or_create_peer_dm(b, a, title="协作")
    assert r1 == r2
    assert store.rooms.conversation_kind(r1) == KIND_PEER_DM
    assert store.get_role_id(r1)  # placeholder 不炸
    conv = store.get(r1)
    assert conv["kind"] == KIND_PEER_DM
    assert set(store.rooms.list_role_participants(r1)) == {a, b}


def test_find_active_ignores_peer_dm(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="研究员")
    owner = store.create(role_id=DEFAULT_ROLE_ID)
    store.append_exchange(owner, "你好", {"role": "assistant", "text": "在"})
    peer = store.rooms.find_or_create_peer_dm(
        DEFAULT_ROLE_ID, other["id"], title="协作"
    )
    store.append_room_inbound(
        peer,
        text="去做X",
        speaker_kind="role",
        speaker_id=DEFAULT_ROLE_ID,
        speaker_name="通用",
        hop=1,
    )
    tip = store.find_active_conversation_id(DEFAULT_ROLE_ID, idle_hours=24)
    assert tip == owner
    assert tip != peer


def test_list_timeline_includes_peer_room(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="游戏开发助手")
    owner = store.create()
    store.append_exchange(owner, "喊他", {"role": "assistant", "text": "好"})
    peer = store.rooms.find_or_create_peer_dm(
        DEFAULT_ROLE_ID, other["id"], title="协作"
    )
    store.append_room_inbound(
        peer,
        text="去做登录页",
        speaker_kind="role",
        speaker_id=DEFAULT_ROLE_ID,
        hop=1,
    )
    segs, _ = store.list_timeline(DEFAULT_ROLE_ID, tip_id=owner)
    ids = {s["id"] for s in segs}
    assert peer in ids
    peer_seg = next(s for s in segs if s["id"] == peer)
    assert peer_seg["kind"] == KIND_PEER_DM
    assert peer_seg["peer_role_id"] == other["id"]

    segs_b, _ = store.list_timeline(other["id"])
    assert any(s["id"] == peer for s in segs_b)


def test_send_message_starts_and_queues(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="游戏开发助手")
    started = []

    def starter(**kwargs):
        started.append(kwargs)
        return {"turn_id": "t1", "status": "running"}

    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(starter)
    owner = store.create()
    store.begin_turn(owner, "去喊游戏开发助手做登录页", "c1")

    result = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        conversation_id=owner,
        to_role_name="游戏开发助手",
        text="请把登录页演示数据换成真实接口",
    )
    assert result.get("error") is None
    assert result["wake_status"] == "started"
    assert result["target_role_id"] == other["id"]
    assert started and started[0]["stimulus"].responding_role_id == other["id"]
    room = result["room_id"]
    msgs = store.get(room)["messages"]
    assert any(m.get("speaker_kind") == "role" and "登录页" in m["text"] for m in msgs)

    # 对方正忙则排队
    store.begin_turn(room, "占住", "busy-b", stimulus=started[0]["stimulus"])
    result2 = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        conversation_id=owner,
        to_role_id=other["id"],
        text="再改一版",
    )
    assert result2["wake_status"] == "queued"


def test_hop_limit(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="游戏开发助手")
    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(lambda **kw: {"turn_id": "t", "status": "running"})
    owner = store.create()
    turn = store.begin_turn(owner, "去喊他", "u1")
    # 把入站 hop 抬到 4
    inbound = store.get_turn_inbound(turn["turn_id"])
    store.conn.execute(
        "UPDATE messages SET hop = 4, causation_id = ? WHERE id = ?",
        (inbound["id"], inbound["id"]),
    )
    store.conn.commit()
    result = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        conversation_id=owner,
        to_role_id=other["id"],
        text="再派一次",
    )
    assert result.get("error") == "hop_limit"


def test_transcript_remaps_peer_inbound(tmp_path):
    store = _conv(tmp_path)
    cid = store.create()
    store.append_room_inbound(
        cid,
        text="请做登录页",
        speaker_kind="role",
        speaker_id="game",
        speaker_name="游戏开发助手",
    )
    store.append_messages(cid, [{"role": "assistant", "text": "做好了"}])
    hist = ConversationTranscript.llm_history(
        store.get(cid), responding_role_id=DEFAULT_ROLE_ID
    )
    assert hist[0]["role"] == "user"
    assert "<peer_message" in hist[0]["content"]
    assert "游戏开发助手" in hist[0]["content"]
    assert hist[1]["role"] == "assistant"


def test_dialogue_turns_peer_not_owner(tmp_path):
    store = _conv(tmp_path)
    cid = store.create()
    store.append_room_inbound(
        cid,
        text="主人喜欢吃香菜",
        speaker_kind="role",
        speaker_id="other",
    )
    turns = store.list_dialogue_turns(cid)
    assert turns[0][0] == "assistant"
    assert store.list_user_messages_text(cid) == []


def test_select_tools_hides_send_without_messaging():
    names = {d["function"]["name"] for d in select_tools(MODE_DEFAULT, True)}
    assert "send_message" not in names
    assert "list_roles" not in names
    names2 = {
        d["function"]["name"]
        for d in select_tools(MODE_DEFAULT, True, role_messaging=True)
    }
    assert "send_message" in names2
    assert "list_roles" in names2


def test_format_peer_message_wraps():
    text = format_peer_message(
        from_name="通用助手大师", from_role_id="default", text="去做X"
    )
    assert 'from="通用助手大师"' in text
    assert "去做X" in text


def test_peer_room_placeholder_not_in_list_all(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="B")
    peer = store.rooms.find_or_create_peer_dm(
        DEFAULT_ROLE_ID, other["id"], title="协作"
    )
    ids = {c["id"] for c in store.list_all(role_id=DEFAULT_ROLE_ID)}
    assert peer not in ids
    row = store.conn.execute(
        "SELECT role_id FROM conversations WHERE id = ?", (peer,)
    ).fetchone()
    assert row["role_id"] == ROOM_ROLE_PLACEHOLDER
