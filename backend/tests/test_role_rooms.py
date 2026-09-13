from app.engine.agent.prompts import MODE_API, MODE_DEFAULT
from app.engine.agent.tool_catalog import select_tools
from app.engine.conversation.transcript import ConversationTranscript
from app.engine.conversations import ConversationStore
from app.engine.rooms.delivery import RoomDelivery
from app.engine.rooms.schema import KIND_OWNER_DM, KIND_PEER_DM, ROOM_ROLE_PLACEHOLDER
from app.engine.rooms.types import format_peer_message
from app.engine.roles import (
    DEFAULT_ROLE_ID,
    VISIBILITY_HIDDEN,
    RoleStore,
    list_sidebar_roles,
)


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
    assert "list_rooms" not in names
    assert "create_room" not in names
    assert "list_roles" in names
    names2 = {
        d["function"]["name"]
        for d in select_tools(MODE_DEFAULT, True, role_messaging=True)
    }
    assert "send_message" in names2
    assert "list_roles" in names2
    assert "list_rooms" in names2
    assert "create_room" in names2


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


def test_create_group_and_mention_wake(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    a = DEFAULT_ROLE_ID
    b = roles.create(name="游戏开发助手")["id"]
    c = roles.create(name="研究员")["id"]
    started = []

    def starter(**kwargs):
        started.append(kwargs)
        return {"turn_id": "tg1", "status": "running"}

    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(starter)
    group = delivery.create_group(title="三人组", role_ids=[a, b, c])["id"]
    assert store.rooms.conversation_kind(group) == "group"
    assert set(store.rooms.list_role_participants(group)) == {a, b, c}

    posted = delivery.send_from_role(
        from_role_id=a,
        room_id=group,
        text="大家看看这个方案",
    )
    assert posted["wake_status"] == "posted"
    assert started == []

    woke = delivery.send_from_role(
        from_role_id=a,
        room_id=group,
        mentions=["游戏开发助手"],
        text="请改登录页",
    )
    assert woke["wake_status"] == "started"
    assert woke["target_role_id"] == b
    assert started and started[0]["stimulus"].responding_role_id == b
    assert started[0]["conversation_id"] == group


def test_owner_interject_peer_wakes_last(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="游戏开发助手")
    started = []

    def starter(**kwargs):
        started.append(kwargs)
        return {"turn_id": "to1", "status": "running"}

    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(starter)
    room = store.rooms.find_or_create_peer_dm(
        DEFAULT_ROLE_ID, other["id"], title="协作"
    )
    store.append_room_inbound(
        room,
        text="先做一版",
        speaker_kind="role",
        speaker_id=other["id"],
        speaker_name="游戏开发助手",
        hop=1,
    )
    result = delivery.send_from_owner(room_id=room, text="补上错误提示")
    assert result["wake_status"] == "started"
    assert result["target_role_id"] == other["id"]
    assert started[0]["stimulus"].is_owner()


def test_owner_group_no_mention_no_wake(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="研究员")
    started = []
    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(
        lambda **kw: started.append(kw) or {"turn_id": "x", "status": "running"}
    )
    group = store.rooms.create_group(
        title="群", role_ids=[DEFAULT_ROLE_ID, other["id"]]
    )
    result = delivery.send_from_owner(room_id=group, text="先记一笔")
    assert result["wake_status"] == "posted"
    assert started == []
    named = delivery.send_from_owner(
        room_id=group, text="@研究员 看一下这段"
    )
    assert named["wake_status"] == "started"
    assert named["target_role_id"] == other["id"]
    assert started and started[0]["stimulus"].responding_role_id == other["id"]
    msgs = store.get(group)["messages"]
    assert any(m.get("speaker_kind") == "user" and "先记一笔" in m["text"] for m in msgs)


def test_collab_status_queued(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="游戏开发助手")
    started = []

    def starter(**kwargs):
        started.append(kwargs)
        return {"turn_id": "t", "status": "running"}

    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(starter)
    owner = store.create()
    store.begin_turn(owner, "去喊他", "c1")
    first = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        conversation_id=owner,
        to_role_id=other["id"],
        text="先做登录页",
    )
    room = first["room_id"]
    store.begin_turn(room, "占住", "busy-b", stimulus=started[0]["stimulus"])
    queued = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        conversation_id=owner,
        to_role_id=other["id"],
        text="再改一版",
    )
    assert queued["wake_status"] == "queued"
    status = delivery.collab_status(room)
    assert status["state"] in {"queued", "working"}
    assert status["queued_count"] >= 1


def test_rooms_http_create_list_and_status(client):
    roles = client.get("/api/roles").json()["roles"]
    default_id = next(r["id"] for r in roles if r.get("is_default"))
    created = client.post(
        "/api/roles",
        json={"name": "游戏开发助手", "system_prompt": "做游戏"},
    )
    assert created.status_code == 200
    other_id = created.json()["id"]
    room = client.post(
        "/api/rooms",
        json={"title": "登录页", "role_ids": [default_id, other_id]},
    )
    assert room.status_code == 200, room.text
    rid = room.json()["id"]
    listed = client.get("/api/rooms", params={"kind": "group"})
    assert listed.status_code == 200
    assert any(r["id"] == rid for r in listed.json()["rooms"])
    status = client.get(f"/api/rooms/{rid}/status")
    assert status.status_code == 200
    assert status.json()["kind"] == "group"
    posted = client.post(
        f"/api/rooms/{rid}/messages",
        json={"text": "先记一笔"},
    )
    assert posted.status_code == 200
    assert posted.json()["wake_status"] == "posted"
    woke = client.post(
        f"/api/rooms/{rid}/messages",
        json={"text": "@游戏开发助手 改登录页"},
    )
    assert woke.status_code == 200
    assert woke.json()["wake_status"] in {"started", "queued"}


def test_hidden_role_not_in_messaging(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    hidden = roles.create(
        name="API工人",
        visibility=VISIBILITY_HIDDEN,
        role_id="api_hidden1",
        onboarding_status="completed",
    )
    assert all(r["id"] != hidden["id"] for r in list_sidebar_roles(roles))
    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(lambda **kw: {"turn_id": "t", "status": "running"})
    owner = store.create()
    store.begin_turn(owner, "喊隐藏角色", "c1")
    try:
        delivery.send_from_role(
            from_role_id=DEFAULT_ROLE_ID,
            conversation_id=owner,
            to_role_id=hidden["id"],
            text="去做X",
        )
        raise AssertionError("hidden role should not be resolvable")
    except ValueError as e:
        assert "找不到" in str(e)
    try:
        delivery.send_from_role(
            from_role_id=DEFAULT_ROLE_ID,
            conversation_id=owner,
            to_role_name="API工人",
            text="去做X",
        )
        raise AssertionError("hidden name should not resolve")
    except ValueError as e:
        assert "找不到" in str(e)
    try:
        delivery.create_group(
            title="不该建",
            role_ids=[DEFAULT_ROLE_ID, hidden["id"]],
        )
        raise AssertionError("hidden role should not join a group")
    except ValueError as e:
        assert "找不到" in str(e)


def test_peer_receipt_wakes_owner_tip_followup_stays_in_peer(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="游戏开发助手")
    started = []

    def starter(**kwargs):
        started.append(kwargs)
        return {"turn_id": f"t{len(started)}", "status": "running"}

    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(starter)
    owner = store.create()
    store.begin_turn(owner, "去喊他", "u1")
    first = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        conversation_id=owner,
        to_role_id=other["id"],
        text="请改登录页",
    )
    room = first["room_id"]
    assert started[0]["conversation_id"] == room
    assert started[0]["stimulus"].responding_role_id == other["id"]
    store.finalize_turn(
        owner,
        turn_id=store.get(owner)["active_turn_id"],
        assistant={"role": "assistant", "text": "已派给同学"},
    )

    receipt = delivery.send_from_role(
        from_role_id=other["id"],
        conversation_id=room,
        to_role_id=DEFAULT_ROLE_ID,
        text="登录页已接上真实接口",
    )
    assert receipt["wake_status"] == "started"
    assert started[1]["conversation_id"] == owner
    assert started[1]["stimulus"].responding_role_id == DEFAULT_ROLE_ID

    follow = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        conversation_id=owner,
        to_role_id=other["id"],
        text="再补错误提示",
    )
    assert follow["wake_status"] == "started"
    assert started[2]["conversation_id"] == room
    assert started[2]["stimulus"].responding_role_id == other["id"]


def test_get_role_id_peer_uses_last_responder(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    other = roles.create(name="游戏开发助手")
    room = store.rooms.find_or_create_peer_dm(
        DEFAULT_ROLE_ID, other["id"], title="协作"
    )
    from app.engine.rooms.types import InboundStimulus, Actor
    from app.engine.rooms.schema import ACTOR_ROLE

    stimulus = InboundStimulus(
        text="去做X",
        speaker=Actor(kind=ACTOR_ROLE, id=DEFAULT_ROLE_ID),
        responding_role_id=other["id"],
        hop=1,
    )
    store.begin_turn(room, "去做X", "busy-b", stimulus=stimulus)
    store.finalize_turn(
        room,
        turn_id=store.get(room)["active_turn_id"],
        assistant={"role": "assistant", "text": "好"},
    )
    assert store.get_role_id(room) == other["id"]


def test_room_lock_queues_second_speaker(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    b = roles.create(name="游戏开发助手")["id"]
    c = roles.create(name="研究员")["id"]
    started = []

    def starter(**kwargs):
        started.append(kwargs)
        return {"turn_id": f"t{len(started)}", "status": "running"}

    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(starter)
    group = delivery.create_group(title="三人组", role_ids=[DEFAULT_ROLE_ID, b, c])["id"]
    first = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        room_id=group,
        mentions=["游戏开发助手"],
        text="@游戏开发助手 先改登录页",
    )
    assert first["wake_status"] == "started"
    store.begin_turn(group, "占住", "busy-b", stimulus=started[0]["stimulus"])
    second = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        room_id=group,
        mentions=["研究员"],
        text="@研究员 写文档",
    )
    assert second["wake_status"] == "queued"


def test_finalize_drains_other_role_queued_in_same_room(tmp_path):
    store = _conv(tmp_path)
    roles = _roles(tmp_path)
    b = roles.create(name="游戏开发助手")["id"]
    c = roles.create(name="研究员")["id"]
    started = []

    def starter(**kwargs):
        started.append(kwargs)
        return {"turn_id": f"t{len(started)}", "status": "running"}

    delivery = RoomDelivery(store, roles)
    delivery.bind_starter(starter)
    store._after_turn_finalized = delivery.drain_role
    group = delivery.create_group(title="三人组", role_ids=[DEFAULT_ROLE_ID, b, c])["id"]
    first = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        room_id=group,
        mentions=["游戏开发助手"],
        text="@游戏开发助手 先改登录页",
    )
    assert first["wake_status"] == "started"
    turn = store.begin_turn(group, "占住", "busy-b", stimulus=started[0]["stimulus"])
    second = delivery.send_from_role(
        from_role_id=DEFAULT_ROLE_ID,
        room_id=group,
        mentions=["研究员"],
        text="@研究员 写文档",
    )
    assert second["wake_status"] == "queued"
    assert len(started) == 1
    store.finalize_turn(
        group,
        turn_id=turn["turn_id"],
        assistant={"role": "assistant", "text": "登录页好了"},
    )
    assert len(started) == 2
    assert started[1]["stimulus"].responding_role_id == c


def test_select_tools_api_mode_hides_messaging():
    names = {
        d["function"]["name"]
        for d in select_tools(
            MODE_API, True, role_messaging=True, sandbox_enabled=True
        )
    }
    assert "send_message" not in names
    assert "list_rooms" not in names
    assert "create_room" not in names
    assert "list_roles" in names
