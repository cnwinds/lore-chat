from app.engine.pending import PendingStore


def test_create_and_get(tmp_path):
    ps = PendingStore(tmp_path / "pending.json")
    qid = ps.create(
        question="这条内容和已有《docker 命令》重叠，如何处理？",
        options=[{"id": "merge", "label": "合并进 docker 命令"},
                 {"id": "new", "label": "新建文档"}],
        payload={"content": "docker logs 用法", "candidate": "技术/docker/常用命令.md"},
    )
    q = ps.get(qid)
    assert q["status"] == "open"
    assert q["payload"]["content"] == "docker logs 用法"


def test_list_open(tmp_path):
    ps = PendingStore(tmp_path / "pending.json")
    ps.create("q1", [{"id": "a", "label": "A"}], {})
    qid2 = ps.create("q2", [{"id": "a", "label": "A"}], {})
    ps.resolve(qid2, "a")
    open_qs = ps.list_open()
    assert len(open_qs) == 1 and open_qs[0]["question"] == "q1"


def test_resolve_sets_choice(tmp_path):
    ps = PendingStore(tmp_path / "pending.json")
    qid = ps.create("q", [{"id": "merge", "label": "M"}], {"x": 1})
    q = ps.resolve(qid, "merge")
    assert q["status"] == "resolved" and q["choice"] == "merge"


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "pending.json"
    ps = PendingStore(path)
    qid = ps.create("q", [{"id": "a", "label": "A"}], {})
    ps2 = PendingStore(path)
    assert ps2.get(qid)["question"] == "q"
