"""按剧本驱动真实 API 跑出演示内容。

跑之前确认目标实例：DEMO_MODE=0、KB 为空、模型链与搜索 provider 已配置。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import httpx
import yaml

# 系统层目录受保护：/api/kb/import 会 403，导入须走整篇覆盖（PUT /api/doc）。
SYSTEM_DIR = "系统"


def load_script(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_script(script: dict) -> list[str]:
    problems: list[str] = []
    conversations = script.get("conversations") or []
    if not conversations:
        problems.append("剧本没有任何会话")
    seen: set[str] = set()
    for index, conv in enumerate(conversations):
        key = conv.get("key")
        if not key:
            problems.append(f"第 {index + 1} 条会话缺少 key")
        elif key in seen:
            problems.append(f"会话 key 重复：{key}")
        else:
            seen.add(key)
        if not (conv.get("turns") or []):
            problems.append(f"会话 {key or index + 1} 没有任何轮次")
        for turn_index, turn in enumerate(conv.get("turns") or []):
            if not (turn.get("text") or "").strip():
                problems.append(f"会话 {key} 第 {turn_index + 1} 轮缺少 text")
    return problems


def _login(client: httpx.Client, password: str) -> None:
    r = client.post("/api/auth/login", json={"password": password})
    r.raise_for_status()


def _authenticate(
    client: httpx.Client, password: str | None, session_cookie: str | None
) -> None:
    if session_cookie:
        client.cookies.set("lorechat_session", session_cookie)
        status = client.get("/api/auth/status")
        status.raise_for_status()
        if not status.json().get("authenticated"):
            raise SystemExit("session cookie 无效或已过期")
        return
    if not password:
        raise SystemExit("需要 --password 或 --session-cookie")
    _login(client, password)


def _overwrite_doc(client: httpx.Client, rel_path: str, text: str) -> None:
    r = client.put("/api/doc", json={"path": rel_path, "body": text})
    r.raise_for_status()


def _import_assets(client: httpx.Client, assets_dir: Path) -> int:
    count = 0
    root = assets_dir / "knowledge"
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        rel_posix = rel.as_posix()
        text = path.read_text(encoding="utf-8")
        if rel.parts[0] == SYSTEM_DIR:
            # 系统层文件由 app 侧播种，这里覆盖成演示人设的版本
            _overwrite_doc(client, rel_posix, text)
            count += 1
            continue
        directory = str(rel.parent).replace("\\", "/")
        directory = "" if directory == "." else directory
        r = client.post(
            "/api/kb/import",
            files={"file": (rel.name, path.read_bytes(), "text/markdown")},
            data={"directory": directory},
        )
        if r.status_code == 409:
            # 重跑：同名文件已在，改为整篇覆盖，保持脚本可重复执行
            _overwrite_doc(client, rel_posix, text)
        else:
            r.raise_for_status()
        count += 1
    return count


def _enable_skills(client: httpx.Client, roots: list[str]) -> None:
    client.put("/api/enabled-skills", json={"roots": roots}).raise_for_status()


def _run_turn(client: httpx.Client, cid: str, turn: dict) -> None:
    with client.stream(
        "POST",
        "/api/chat",
        json={
            "text": turn["text"],
            "conversation_id": cid,
            "web_enabled": bool(turn.get("web_enabled")),
            "doc_context": turn.get("doc_context") or [],
        },
        timeout=600.0,
    ) as response:
        response.raise_for_status()
        saw_error = False
        for line in response.iter_lines():
            if line.startswith("event: error"):
                saw_error = True
            elif saw_error and line.startswith("data: "):
                raise SystemExit(f"回合失败：{line[6:]}")
            elif line.startswith("event: done"):
                return
        raise SystemExit("回合结束但未收到 done 事件，检查实例日志")


def _ensure_kb_indexed(client: httpx.Client) -> None:
    """会话之间强制全量重建检索索引，避免下一会话 search_kb 仍看到空索引。"""
    r = client.post("/api/admin/reindex")
    if r.status_code == 401:
        print("  警告：无管理员权限，跳过 reindex")
        return
    r.raise_for_status()
    print("  已 reindex")


def run(
    base_url: str,
    password: str | None,
    script_path: Path,
    assets_dir: Path,
    pause: float,
    session_cookie: str | None = None,
    only_keys: set[str] | None = None,
    skip_import: bool = False,
) -> None:
    script = load_script(script_path)
    problems = validate_script(script)
    if problems:
        raise SystemExit("剧本校验失败：\n" + "\n".join(problems))

    conversations = list(script["conversations"])
    if only_keys:
        conversations = [c for c in conversations if c.get("key") in only_keys]
        missing = only_keys - {c.get("key") for c in conversations}
        if missing:
            raise SystemExit("剧本里没有这些 key：" + ", ".join(sorted(missing)))

    with httpx.Client(base_url=base_url, timeout=60.0, follow_redirects=True) as client:
        _authenticate(client, password, session_cookie)
        if skip_import:
            print("跳过前置资产导入")
        else:
            imported = _import_assets(client, assets_dir)
            print(f"已导入前置资产 {imported} 篇")
            _ensure_kb_indexed(client)

        for conv in conversations:
            _enable_skills(client, conv.get("skills") or [])
            cid = client.post("/api/conversations").json()["id"]
            print(f"[{conv['key']}] conversation_id={cid}")
            for index, turn in enumerate(conv["turns"], start=1):
                print(f"  第 {index} 轮…")
                _run_turn(client, cid, turn)
                time.sleep(pause)
            # 本会话可能写入了文档；下一会话检索前先刷索引
            _ensure_kb_indexed(client)


def main() -> None:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="按剧本真跑演示内容")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--password", default="", help="目标实例的管理员密码")
    parser.add_argument(
        "--session-cookie",
        default="",
        help="已登录的 lorechat_session；与 --password 二选一",
    )
    parser.add_argument("--script", type=Path, default=here / "script.yaml")
    parser.add_argument("--assets", type=Path, default=here.parent / "assets")
    parser.add_argument("--pause", type=float, default=2.0, help="轮次间隔秒数")
    parser.add_argument(
        "--only",
        default="",
        help="只跑这些会话 key，逗号分隔；默认全部",
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="不导入前置资产（在已有 KB 上补跑某条会话时用）",
    )
    args = parser.parse_args()
    only = {k.strip() for k in args.only.split(",") if k.strip()}
    run(
        args.base_url,
        args.password or None,
        args.script,
        args.assets,
        args.pause,
        session_cookie=args.session_cookie or None,
        only_keys=only or None,
        skip_import=args.skip_import,
    )


if __name__ == "__main__":
    main()
