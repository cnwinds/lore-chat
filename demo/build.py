"""把 demo/ 的纯文本内容物化成运行时知识库。

部署与重置是同一条路径：演示站容器每次启动跑一次，运行期漂移自动消失。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.load import read_and_load  # noqa: E402
from tools.timeshift import compute_offset_days  # noqa: E402


def _ensure_app_importable() -> None:
    """让 `app` 包可导入：仓库里在 ../backend，镜像里在 demo/ 同级。"""
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "backend", here.parent):
        if (candidate / "app" / "__init__.py").is_file():
            path = str(candidate)
            if path not in sys.path:
                sys.path.insert(0, path)
            return


def _wipe(kb_path: Path) -> None:
    """清空知识库目录内容。挂载点本身不可删（Docker bind mount 会 Device busy）。"""
    if not kb_path.exists():
        kb_path.mkdir(parents=True, exist_ok=True)
        return
    for child in kb_path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _copy_knowledge(content_dir: Path, kb_path: Path) -> int:
    src = content_dir / "knowledge"
    if not src.is_dir():
        return 0
    shutil.copytree(src, kb_path, dirs_exist_ok=True)
    return sum(1 for _ in kb_path.rglob("*.md"))


def _init_schema(kb_path: Path) -> str:
    """借 app 侧建表，避免在 demo 工具里复制一份会漂移的 DDL。返回 workspace id。"""
    _ensure_app_importable()
    from app.engine.conversations import ConversationStore
    from app.engine.memory.store import MemoryStore
    from app.engine.workspace import ensure_workspace_id

    workspace_id = ensure_workspace_id(kb_path)
    ConversationStore(kb_path / ".kb" / "conversations")
    MemoryStore(kb_path / ".kb" / "memory" / "memory.db", owner_key=workspace_id)
    return workspace_id


def _reindex(kb_path: Path) -> None:
    _ensure_app_importable()
    from app.backup.reindex import reindex_all
    from app.config import Settings
    from app.deps import build_container

    settings = Settings(kb_path=kb_path)
    reindex_all(build_container(settings))


def materialize(
    content_dir: Path,
    kb_path: Path,
    today: date | None = None,
    reindex: bool = True,
) -> dict:
    manifest = json.loads((content_dir / "manifest.json").read_text(encoding="utf-8"))
    offset = compute_offset_days(manifest["reference_date"], today or date.today())

    _wipe(kb_path)
    docs = _copy_knowledge(content_dir, kb_path)
    workspace_id = _init_schema(kb_path)
    read_and_load(kb_path, content_dir, offset_days=offset, owner_key=workspace_id)

    conv_dir = content_dir / "conversations"
    conversations = len(list(conv_dir.glob("*.json"))) if conv_dir.is_dir() else 0

    if reindex:
        _reindex(kb_path)

    return {"docs": docs, "conversations": conversations, "offset_days": offset}


def main() -> None:
    parser = argparse.ArgumentParser(description="构建演示站运行时知识库")
    parser.add_argument("--kb", required=True, type=Path)
    parser.add_argument("--content", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--no-reindex", action="store_true")
    args = parser.parse_args()
    result = materialize(args.content, args.kb, reindex=not args.no_reindex)
    print(
        f"已构建：{result['docs']} 篇文档、{result['conversations']} 条会话、"
        f"时间平移 {result['offset_days']} 天"
    )


if __name__ == "__main__":
    main()
