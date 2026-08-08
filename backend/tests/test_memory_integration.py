from app.engine.agent.tools import select_tools
from app.engine.memory.constants import MEMORY_DOC_REL


def test_put_memory_doc_is_rejected(client):
    container = client.app.state.container
    container.memory_service.remember("记住我喜欢茶")
    r = client.put(
        "/api/doc",
        json={"path": MEMORY_DOC_REL, "body": "# 记忆 · 关于用户\n\n- hack\n"},
    )
    assert r.status_code == 400
    assert "数据库" in r.json()["detail"] or "设置" in r.json()["detail"]
    # 未通过文件写入复活/新增
    confirmed = container.memory_service.store.list_confirmed()
    assert any("茶" in f["statement"] for f in confirmed)
    assert not any("hack" in f["statement"] for f in confirmed)


def test_memory_tools_gated_by_mode():
    names = {d["function"]["name"] for d in select_tools("no_write", web_enabled=True)}
    assert "manage_memory" not in names
    assert "recall_memory" in names
