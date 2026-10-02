"""房间（peer_dm / group）记忆抽取与游标。"""


from app.engine.conversations import ConversationStore
from app.engine.memory.cards import KnowledgeCards, role_scope
from app.engine.memory.constants import ROOM_WINDOW_MAX_MESSAGES
from app.engine.memory.resolver import SlotAction
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.memory_worker import MemoryWorker
from app.engine.roles import RoleStore, VISIBILITY_HIDDEN
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer, preference_action


def _room_worker(tmp_path, *, owner_ext=None, card_ext=None, roles=None, conv=None):
    conv = conv or ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    roles = roles or RoleStore(tmp_path / "roles")
    cards = KnowledgeCards(
        tmp_path / "memory.db", owner=svc, roles=roles, conversations=conv
    )

    class _Owner:
        def extract(self, turns, *, confirmed_summary):
            del confirmed_summary
            if owner_ext:
                return owner_ext(turns)
            return []

    class _Card:
        def extract(self, *_a, **_k):
            return []

        def extract_room(self, room, *, lens, existing_cards, owner_summary):
            del existing_cards, owner_summary
            if card_ext:
                return card_ext(room, lens=lens)
            return []

    worker = MemoryWorker(
        conv,
        svc,
        extractor=_Owner(),
        cards=cards,
        card_extractor=_Card(),
        idle_hours=0,
    )
    return conv, roles, cards, svc, worker


def _insert_msg(conv, cid, *, seq, text, speaker_kind, speaker_id, speaker_name=None, status="complete"):
    conv.conn.execute(
        """
        INSERT INTO messages(
            id, conversation_id, seq, role, text, ts, status,
            speaker_kind, speaker_id, speaker_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"m{seq}",
            cid,
            seq,
            "user" if speaker_kind == "user" else "assistant",
            text,
            f"2026-01-01T00:00:{seq:02d}Z",
            status,
            speaker_kind,
            speaker_id,
            speaker_name,
        ),
    )
    conv.conn.commit()


def test_group_owner_message_marks_dirty_and_ts(tmp_path):
    conv, roles, *_ = _room_worker(tmp_path)
    a = roles.create(name="A", system_prompt="")
    b = roles.create(name="B", system_prompt="")
    gid = conv.rooms.create_group(title="群", role_ids=[a["id"], b["id"]])
    msg = conv.append_room_inbound(
        gid,
        text="主人说",
        speaker_kind="user",
        speaker_id="owner",
    )
    row = conv.conn.execute(
        "SELECT memory_dirty, last_user_message_at FROM conversations WHERE id = ?",
        (gid,),
    ).fetchone()
    assert row["memory_dirty"] == 1
    assert row["last_user_message_at"] == msg["ts"]


def test_role_reply_finalize_marks_dirty(tmp_path):
    conv, roles, _, _, worker = _room_worker(tmp_path)
    a = roles.create(name="A", system_prompt="")
    b = roles.create(name="B", system_prompt="")
    gid = conv.rooms.create_group(title="群", role_ids=[a["id"], b["id"]])
    turn = conv.begin_turn(gid, "主人问", "c1")
    conv.finalize_turn(
        gid,
        turn["turn_id"],
        assistant={"text": "角色答", "status": "complete", "ts": "2026-09-30T00:00:00Z"},
    )
    row = conv.conn.execute(
        "SELECT memory_dirty, last_user_message_at FROM conversations WHERE id = ?",
        (gid,),
    ).fetchone()
    assert row["memory_dirty"] == 1
    assert row["last_user_message_at"] == "2026-09-30T00:00:00Z"


def test_system_stimulus_does_not_mark_dirty(tmp_path):
    conv, roles, *_ = _room_worker(tmp_path)
    a = roles.create(name="A", system_prompt="")
    b = roles.create(name="B", system_prompt="")
    gid = conv.rooms.create_group(title="群", role_ids=[a["id"], b["id"]])
    conv.append_room_inbound(
        gid,
        text="刺激",
        speaker_kind="system",
        speaker_id="system",
    )
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (gid,)
    ).fetchone()
    assert row["memory_dirty"] == 0
    conv.append_room_inbound(
        gid,
        text="   ",
        speaker_kind="role",
        speaker_id=a["id"],
    )
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (gid,)
    ).fetchone()
    assert row["memory_dirty"] == 0


def test_owner_dm_dirty_unchanged(tmp_path):
    conv = ConversationStore(tmp_path / "conversations")
    cid = conv.create()
    conv.begin_turn(cid, "主人私聊", "c1")
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (cid,)
    ).fetchone()
    assert row["memory_dirty"] == 1


def test_sixty_messages_triggers_immediate(tmp_path, monkeypatch):
    conv, roles, *_ = _room_worker(tmp_path)
    a = roles.create(name="A", system_prompt="")
    b = roles.create(name="B", system_prompt="")
    gid = conv.rooms.create_group(title="群", role_ids=[a["id"], b["id"]])
    calls = {"n": 0}

    def _req(cid):
        calls["n"] += 1
        return True

    monkeypatch.setattr(conv.memory_schedule, "request_immediate_unlocked", _req)
    for i in range(1, ROOM_WINDOW_MAX_MESSAGES):
        conv.append_room_inbound(
            gid, text=f"t{i}", speaker_kind="user", speaker_id="owner"
        )
    assert calls["n"] == 0
    conv.append_room_inbound(
        gid, text="t60", speaker_kind="user", speaker_id="owner"
    )
    assert calls["n"] == 1


def test_list_room_window_skips_non_learnable_rows(tmp_path):
    from app.engine.memory.room_window import RoomLine

    conv = ConversationStore(tmp_path / "conversations")
    cid = conv.create()
    conv.conn.execute("UPDATE conversations SET kind = 'group' WHERE id = ?", (cid,))
    conv.conn.commit()
    _insert_msg(conv, cid, seq=1, text="", speaker_kind="user", speaker_id="owner")
    _insert_msg(conv, cid, seq=2, text="sys", speaker_kind="system", speaker_id="s")
    _insert_msg(conv, cid, seq=3, text="主人话", speaker_kind="user", speaker_id="owner")
    _insert_msg(conv, cid, seq=4, text="角色话", speaker_kind="role", speaker_id="r1", speaker_name="A")
    _insert_msg(conv, cid, seq=5, text="半截", speaker_kind="role", speaker_id="r1", status="error")
    _insert_msg(conv, cid, seq=6, text="主人再问", speaker_kind="user", speaker_id="owner")
    owner3 = RoomLine(3, "user", "owner", None, "主人话")
    role4 = RoomLine(4, "role", "r1", "A", "角色话")
    owner6 = RoomLine(6, "user", "owner", None, "主人再问")

    w = conv.list_room_window(cid, after_seq=None, limit=10, context=2)
    assert (w.lines, w.context, w.end_seq, w.has_more) == (
        [owner3, role4, owner6],
        [],
        6,
        False,
    )

    w = conv.list_room_window(cid, after_seq=None, limit=2, context=2)
    assert (w.lines, w.end_seq, w.has_more) == ([owner3, role4], 4, True)

    w = conv.list_room_window(cid, after_seq=4, limit=10, context=2)
    assert (w.lines, w.context, w.end_seq, w.has_more) == (
        [owner6],
        [owner3, role4],
        6,
        False,
    )

    w = conv.list_room_window(cid, after_seq=4, limit=10, context=0)
    assert w.context == []

    w = conv.list_room_window(cid, after_seq=6, limit=10, context=2)
    assert (w.lines, w.end_seq, w.has_more) == ([], None, False)


def test_errored_reply_right_after_cursor_does_not_stall(tmp_path):
    seen = []

    def card_ext(room, *, lens):
        del lens
        seen.append(list(room.lines))
        return []

    conv, roles, cards, svc, worker = _room_worker(tmp_path, card_ext=card_ext)
    ra = roles.create(name="A", system_prompt="")
    rb = roles.create(name="B", system_prompt="")
    gid = conv.rooms.create_group(title="G", role_ids=[ra["id"], rb["id"]])
    _insert_msg(conv, gid, seq=1, text="主人先问", speaker_kind="user", speaker_id="owner")
    _insert_msg(
        conv, gid, seq=2, text="半截", speaker_kind="role", speaker_id=ra["id"], status="error"
    )
    _insert_msg(conv, gid, seq=3, text="主人重问", speaker_kind="user", speaker_id="owner")
    _insert_msg(
        conv, gid, seq=4, text="A答", speaker_kind="role", speaker_id=ra["id"], speaker_name="A"
    )
    conv.memory_schedule.advance_cursor_seq(gid, 1)
    conv.conn.execute(
        "UPDATE conversations SET memory_dirty = 1, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00Z", gid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=2)
    assert seen == [[("主人", "主人重问"), ("本角色", "A答")]]
    assert conv.get_memory_cursor_seq(gid) == 4
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (gid,)
    ).fetchone()
    assert row["memory_dirty"] == 0


def test_group_job_owner_turns_and_dual_lenses(tmp_path):
    owner_turns = []
    rooms_seen = []

    def owner_ext(turns):
        owner_turns.append(list(turns))
        return [preference_action("主人偏好短句")]

    def card_ext(room, *, lens):
        from app.engine.memory.role_card_extractor import RoomDialogue

        rooms_seen.append(
            RoomDialogue(
                kind=room.kind,
                title=room.title,
                peer_names=list(room.peer_names),
                context=list(room.context),
                lines=list(room.lines),
            )
        )
        return [
            SlotAction(
                action="new",
                statement=f"{lens.subject_name}卡",
                category="practice",
                origin="direct",
                confidence=0.9,
                slot_hint="practice.x",
            )
        ]

    conv, roles, cards, svc, worker = _room_worker(
        tmp_path, owner_ext=owner_ext, card_ext=card_ext
    )
    ra = roles.create(name="角色A", system_prompt="A人设")
    rb = roles.create(name="角色B", system_prompt="B人设")
    gid = conv.rooms.create_group(title="产品群", role_ids=[ra["id"], rb["id"]])
    _insert_msg(conv, gid, seq=1, text="主人安排", speaker_kind="user", speaker_id="owner")
    _insert_msg(
        conv,
        gid,
        seq=2,
        text="A回复",
        speaker_kind="role",
        speaker_id=ra["id"],
        speaker_name="角色A",
    )
    _insert_msg(
        conv,
        gid,
        seq=3,
        text="B补充",
        speaker_kind="role",
        speaker_id=rb["id"],
        speaker_name="角色B",
    )
    conv.conn.execute(
        "UPDATE conversations SET memory_dirty = 1, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00Z", gid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=3)
    from app.engine.memory.role_card_extractor import RoomDialogue

    assert owner_turns == [[("user", "主人安排"), ("assistant", "A回复"), ("assistant", "B补充")]]
    assert rooms_seen == [
        RoomDialogue(
            kind="group",
            title="产品群",
            peer_names=["角色B"],
            context=[],
            lines=[
                ("主人", "主人安排"),
                ("本角色", "A回复"),
                ("同伴「角色B」", "B补充"),
            ],
        ),
        RoomDialogue(
            kind="group",
            title="产品群",
            peer_names=["角色A"],
            context=[],
            lines=[
                ("主人", "主人安排"),
                ("同伴「角色A」", "A回复"),
                ("本角色", "B补充"),
            ],
        ),
    ]
    assert [f["statement"] for f in cards.store(role_scope(ra["id"])).list_confirmed()] == [
        "角色A卡"
    ]
    assert [f["statement"] for f in cards.store(role_scope(rb["id"])).list_confirmed()] == [
        "角色B卡"
    ]
    for scope in (role_scope(ra["id"]), role_scope(rb["id"]), "owner"):
        entries = cards.growth_entries(scope, limit=5)
        assert [(e["kind"], e["conversation_id"]) for e in entries] == [("learned", gid)]
    assert conv.get_memory_cursor_seq(gid) == 3
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (gid,)
    ).fetchone()
    assert row["memory_dirty"] == 0


def test_second_run_idle_until_new_messages(tmp_path):
    calls = {"owner": 0, "room": 0}
    rooms = []

    def owner_ext(turns):
        del turns
        calls["owner"] += 1
        return []

    def card_ext(room, *, lens):
        del lens
        calls["room"] += 1
        rooms.append(room)
        return []

    conv, roles, cards, svc, worker = _room_worker(
        tmp_path, owner_ext=owner_ext, card_ext=card_ext
    )
    ra = roles.create(name="A", system_prompt="")
    rb = roles.create(name="B", system_prompt="")
    gid = conv.rooms.create_group(title="G", role_ids=[ra["id"], rb["id"]])
    _insert_msg(conv, gid, seq=1, text="主人", speaker_kind="user", speaker_id="owner")
    _insert_msg(
        conv, gid, seq=2, text="A", speaker_kind="role", speaker_id=ra["id"], speaker_name="A"
    )
    conv.conn.execute(
        "UPDATE conversations SET memory_dirty = 1, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00Z", gid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=2)
    calls["owner"] = 0
    calls["room"] = 0
    worker.drain(max_jobs=2)
    assert calls == {"owner": 0, "room": 0}
    for i, text in enumerate(["n1", "n2", "n3"], start=3):
        _insert_msg(
            conv,
            gid,
            seq=i,
            text=text,
            speaker_kind="role",
            speaker_id=ra["id"],
            speaker_name="A",
        )
    conv.conn.execute(
        "UPDATE conversations SET memory_dirty = 1, last_user_message_at = ? WHERE id = ?",
        ("2026-01-02T00:00:00Z", gid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=2)
    assert calls == {"owner": 0, "room": 1}
    assert rooms[-1].lines == [("本角色", "n1"), ("本角色", "n2"), ("本角色", "n3")]
    assert rooms[-1].context == [("主人", "主人"), ("本角色", "A")]
    assert conv.get_memory_cursor_seq(gid) == 5


def test_peer_dm_skips_owner_extractor(tmp_path):
    calls = {"owner": 0, "room": 0}

    def owner_ext(turns):
        del turns
        calls["owner"] += 1
        return []

    def card_ext(room, *, lens):
        del room, lens
        calls["room"] += 1
        return []

    conv, roles, cards, svc, worker = _room_worker(
        tmp_path, owner_ext=owner_ext, card_ext=card_ext
    )
    ra = roles.create(name="A", system_prompt="")
    rb = roles.create(name="B", system_prompt="")
    pid = conv.rooms.find_or_create_peer_dm(ra["id"], rb["id"], title="互通")
    _insert_msg(
        conv, pid, seq=1, text="A说", speaker_kind="role", speaker_id=ra["id"], speaker_name="A"
    )
    conv.conn.execute(
        "UPDATE conversations SET memory_dirty = 1, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00Z", pid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=2)
    assert calls == {"owner": 0, "room": 1}


def test_max_four_role_lenses_by_speech_count(tmp_path):
    order = []

    def card_ext(room, *, lens):
        order.append(lens.subject_name)
        return []

    conv, roles, cards, svc, worker = _room_worker(tmp_path, card_ext=card_ext)
    ids = [roles.create(name=f"R{i}", system_prompt="")["id"] for i in range(5)]
    gid = conv.rooms.create_group(title="G", role_ids=ids[:2])
    for rid in ids[2:]:
        conv.rooms._add_participant_unlocked(gid, "role", rid, membership="member")
    counts = {ids[0]: 3, ids[1]: 2, ids[2]: 2, ids[3]: 1, ids[4]: 4}
    seq = 1
    for rid, n in counts.items():
        name = roles.get(rid)["name"]
        for j in range(n):
            _insert_msg(
                conv,
                gid,
                seq=seq,
                text=f"{rid}-{j}",
                speaker_kind="role",
                speaker_id=rid,
                speaker_name=name,
            )
            seq += 1
    conv.conn.execute(
        "UPDATE conversations SET memory_dirty = 1, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00Z", gid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=2)
    assert order == ["R4", "R0", "R1", "R2"]


def test_lens_exception_keeps_cursor(tmp_path):
    def card_ext(room, *, lens):
        del room
        if lens.subject_name == "坏":
            raise RuntimeError("boom")
        return []

    conv, roles, cards, svc, worker = _room_worker(tmp_path, card_ext=card_ext)
    good = roles.create(name="好", system_prompt="")
    bad = roles.create(name="坏", system_prompt="")
    gid = conv.rooms.create_group(title="G", role_ids=[good["id"], bad["id"]])
    _insert_msg(
        conv, gid, seq=1, text="g", speaker_kind="role", speaker_id=good["id"], speaker_name="好"
    )
    _insert_msg(
        conv, gid, seq=2, text="b", speaker_kind="role", speaker_id=bad["id"], speaker_name="坏"
    )
    conv.conn.execute(
        "UPDATE conversations SET memory_dirty = 1, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00Z", gid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=2)
    assert conv.get_memory_cursor_seq(gid) is None


def test_hidden_role_skipped(tmp_path):
    order = []

    def card_ext(room, *, lens):
        order.append(lens.subject_name)
        return []

    conv, roles, cards, svc, worker = _room_worker(tmp_path, card_ext=card_ext)
    vis = roles.create(name="可见", system_prompt="")
    hid = roles.create(name="隐藏", system_prompt="", visibility=VISIBILITY_HIDDEN)
    gid = conv.rooms.create_group(title="G", role_ids=[vis["id"], hid["id"]])
    _insert_msg(
        conv,
        gid,
        seq=1,
        text="h",
        speaker_kind="role",
        speaker_id=hid["id"],
        speaker_name="隐藏",
    )
    _insert_msg(
        conv,
        gid,
        seq=2,
        text="v",
        speaker_kind="role",
        speaker_id=vis["id"],
        speaker_name="可见",
    )
    conv.conn.execute(
        "UPDATE conversations SET memory_dirty = 1, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00Z", gid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=2)
    assert order == ["可见"]


def test_window_sixty_keeps_dirty_and_requeues_immediate(tmp_path, monkeypatch):
    immediate = {"n": 0}

    def card_ext(room, *, lens):
        del room, lens
        return []

    conv, roles, cards, svc, worker = _room_worker(tmp_path, card_ext=card_ext)
    ra = roles.create(name="A", system_prompt="")
    rb = roles.create(name="B", system_prompt="")
    gid = conv.rooms.create_group(title="G", role_ids=[ra["id"], rb["id"]])
    for i in range(1, 62):
        _insert_msg(
            conv,
            gid,
            seq=i,
            text=f"m{i}",
            speaker_kind="role",
            speaker_id=ra["id"],
            speaker_name="A",
        )

    def _req(cid):
        immediate["n"] += 1
        return conv.memory_schedule.request_immediate_unlocked(cid)

    monkeypatch.setattr(conv.memory_schedule, "request_immediate", _req)
    conv.conn.execute(
        "UPDATE conversations SET memory_dirty = 1, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00Z", gid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=1)
    assert conv.get_memory_cursor_seq(gid) == 60
    row = conv.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (gid,)
    ).fetchone()
    assert row["memory_dirty"] == 1
    assert immediate["n"] == 1
