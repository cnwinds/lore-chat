from app.engine.agent.tools import select_tools


def test_put_memory_doc_triggers_import(client):
    container = client.app.state.container
    container.memory_service.remember("记住我喜欢茶")
    container.memory_service.render_to_file()
    doc = container.repo.read_doc("系统/记忆.md")
    new_body = doc.body + "\n- 手动添加：不喝咖啡\n"
    r = client.put("/api/doc", json={"path": "系统/记忆.md", "body": new_body})
    assert r.status_code == 200
    confirmed = container.memory_service.store.list_confirmed()
    assert any("不喝咖啡" in f["statement"] for f in confirmed)


def test_select_tools_no_write_excludes_manage_memory():
    names = {d["function"]["name"] for d in select_tools("no_write", web_enabled=True)}
    assert "manage_memory" not in names
    assert "recall_memory" in names
