from __future__ import annotations

from app.storage.repo import KnowledgeRepo


def summarize_kb_structure(repo: KnowledgeRepo, *, max_files_per_dir: int = 15) -> dict:
    """聚合知识库目录树，供 Agent 规划归类路径。"""
    paths = sorted(repo.list_tree())
    by_dir: dict[str, list[str]] = {}
    root_docs: list[str] = []
    protected_paths: list[str] = []

    for rel in paths:
        if not rel.endswith(".md"):
            continue
        if repo.is_protected(rel):
            protected_paths.append(rel)
            continue
        parts = rel.rsplit("/", 1)
        if len(parts) == 1:
            root_docs.append(parts[0])
        else:
            directory, filename = parts[0], parts[1]
            by_dir.setdefault(directory, []).append(filename)

    directories = []
    for directory in sorted(by_dir.keys()):
        files = sorted(by_dir[directory])
        directories.append(
            {
                "path": directory,
                "doc_count": len(files),
                "files": files[:max_files_per_dir],
                "truncated": len(files) > max_files_per_dir,
            }
        )

    top_level = sorted({d.split("/")[0] for d in by_dir} | set(root_docs))
    lines = [
        f"共 {len(paths)} 篇 Markdown；可写目录 {len(directories)} 个"
        + (f"，根目录文档 {len(root_docs)} 篇" if root_docs else "")
    ]
    if directories:
        lines.append("目录示例（path → 文档数）：")
        for item in directories[:40]:
            suffix = "…" if item["truncated"] else ""
            sample = "、".join(item["files"][:5])
            if item["truncated"]:
                sample += "…"
            lines.append(f"- {item['path']}（{item['doc_count']}）{': ' + sample if sample else ''}{suffix}")
        if len(directories) > 40:
            lines.append(f"… 另有 {len(directories) - 40} 个目录未列出")
    if protected_paths:
        lines.append(f"受保护（不可写入/移动/删除）：{', '.join(protected_paths[:8])}"
                     + ("…" if len(protected_paths) > 8 else ""))

    return {
        "summary": "\n".join(lines),
        "top_level_categories": top_level,
        "directories": directories,
        "root_docs": sorted(root_docs),
        "protected_paths": protected_paths,
        "total_docs": len([p for p in paths if p.endswith(".md")]),
    }
