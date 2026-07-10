from app.engine.conversations import ConversationStore


def test_create_and_get(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    cid = store.create()
    conv = store.get(cid)
    assert conv["id"] == cid
    assert conv["title"] == "新对话"
    assert conv["messages"] == []


def test_list_all_sorted_by_updated(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    cid1 = store.create()
    cid2 = store.create()
    store.append_exchange(cid1, "第一条", {"role": "assistant", "text": "回复"})
    items = store.list_all()
    assert len(items) == 2
    assert items[0]["id"] == cid1
    assert items[0]["message_count"] == 2


def test_append_exchange_sets_title(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    cid = store.create()
    store.append_exchange(
        cid,
        "windows终端怎么设置utf8编码",
        {"role": "assistant", "text": "可以用 chcp 65001", "intent": "recall"},
    )
    conv = store.get(cid)
    assert conv["title"] == "windows终端怎么设置utf8编码"
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][1]["text"] == "可以用 chcp 65001"


def test_append_messages(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    cid = store.create()
    store.append_messages(
        cid, [{"role": "assistant", "text": "已保存文件", "intent": "remember"}]
    )
    conv = store.get(cid)
    assert len(conv["messages"]) == 1


def test_delete(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    cid = store.create()
    store.delete(cid)
    try:
        store.get(cid)
        assert False, "should raise"
    except KeyError:
        pass


def test_append_exchange_stores_timeline_and_ts(tmp_path):
    store = ConversationStore(tmp_path / "c.json")
    cid = store.create()
    assistant = {
        "role": "assistant",
        "ts": "2026-07-10T10:00:00+08:00",
        "timeline": [
            {
                "type": "text",
                "ts": "2026-07-10T10:00:01+08:00",
                "content": "hi",
            }
        ],
        "sources": [],
    }
    store.append_exchange(
        cid, "hello", assistant, user_ts="2026-07-10T09:59:00+08:00"
    )
    conv = store.get(cid)
    assert conv["messages"][0]["ts"] == "2026-07-10T09:59:00+08:00"
    assert conv["messages"][1]["timeline"][0]["type"] == "text"


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "conversations.json"
    store = ConversationStore(path)
    cid = store.create()
    store.append_exchange(cid, "hi", {"role": "assistant", "text": "hello"})
    store2 = ConversationStore(path)
    assert len(store2.get(cid)["messages"]) == 2


def test_llm_history_from_timeline(tmp_path):
    store = ConversationStore(tmp_path / "c.json")
    cid = store.create()
    store.append_exchange(
        cid,
        "第一轮问题",
        {
            "role": "assistant",
            "timeline": [
                {"type": "tool", "tool": "search_kb", "summary": "找到 1 条"},
                {"type": "text", "content": "第一轮回答"},
            ],
        },
    )
    store.append_exchange(
        cid,
        "追问一下",
        {"role": "assistant", "text": "第二轮回答"},
    )
    history = ConversationStore.llm_history(store.get(cid))
    assert history == [
        {"role": "user", "content": "第一轮问题"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "追问一下"},
        {"role": "assistant", "content": "第二轮回答"},
    ]


def test_llm_history_truncates_by_turns(tmp_path):
    store = ConversationStore(tmp_path / "c.json")
    cid = store.create()
    for i in range(3):
        store.append_exchange(
            cid,
            f"问题{i}",
            {"role": "assistant", "text": f"回答{i}"},
        )
    history = ConversationStore.llm_history(store.get(cid), max_turns=2)
    assert history == [
        {"role": "user", "content": "问题1"},
        {"role": "assistant", "content": "回答1"},
        {"role": "user", "content": "问题2"},
        {"role": "assistant", "content": "回答2"},
    ]
