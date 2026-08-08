"""一次性迁移：python -m app.engine.memory_migrate_cli [--dry-run] [--render] [--use-llm]"""

from __future__ import annotations

import argparse
import json

from app.config import Settings, get_settings
from app.deps import build_container
from app.engine.memory.migrate_slots import migrate_abstract_slots
from app.settings_store import SettingsStore


def _effective_settings() -> Settings:
    """与线上一致：.env/环境变量为底，再叠知识库 .kb/settings.json（设置页写入的 Key）。"""
    base = get_settings()
    return SettingsStore(base.kb_path, base).get()


def main() -> None:
    parser = argparse.ArgumentParser(description="将旧记忆 slot 合并为抽象谓词")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--render",
        action="store_true",
        help="迁移后打印 DB 直出注入预览（不再写 记忆.md）",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="调用迁移专用 LLM 分配抽象槽与 canonical（失败回退启发式）",
    )
    args = parser.parse_args()
    settings = _effective_settings()
    container = build_container(settings)
    llm = container.llm if args.use_llm else None
    if args.use_llm:
        key = (settings.openai_api_key or "").strip()
        print(
            "llm_key_source=settings_store",
            f"kb_path={settings.kb_path}",
            f"key_prefix={key[:6]}…" if len(key) > 6 else f"key={key!r}",
        )
    result = migrate_abstract_slots(
        container.memory_service.store, dry_run=args.dry_run, llm=llm
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.render and not args.dry_run:
        preview = container.memory_service.render_context()
        print("context_preview_chars", len(preview))
        print(preview[:2000])


if __name__ == "__main__":
    main()
