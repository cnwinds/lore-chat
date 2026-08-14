from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from app.index.extract import extract_text
from app.index.indexer import Indexer
from app.storage import frontmatter
from app.storage.kb_paths import (
    KbPathError,
    join_kb_directory,
    join_kb_path,
    normalize_directory,
    title_from_rel_path,
)
from app.engine.kb_markdown_images import sanitize_markdown_image_srcs_for_storage
from app.engine.memory.constants import is_memory_projection_path
from app.engine.write_policy import WriteMode
from app.storage.kb_media_paths import is_image_filename
from app.storage.kb_text_files import is_kb_text_file
from app.storage.repo import KnowledgeRepo

if TYPE_CHECKING:
    from app.engine.placement import PlacementDecision

_MEMORY_FILE_DISABLED_MSG = (
    "记忆已改由数据库管理，请到设置 → 记忆中编辑，或使用 manage_memory"
)


class KbPathExistsError(FileExistsError):
    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        super().__init__(f"目标路径已存在：{rel_path}")


def is_markdown_path(rel_path: str) -> bool:
    return rel_path.replace("\\", "/").lower().endswith(".md")


def suggest_alternate_filename(filename: str) -> str:
    base = _safe_basename(filename)
    stem = PurePosixPath(base).stem
    suffix = PurePosixPath(base).suffix
    m = re.match(r"^(.+) \((\d+)\)$", stem)
    if m:
        b, n = m.group(1), int(m.group(2))
        return f"{b} ({n + 1}){suffix}"
    return f"{stem} (1){suffix}"


def _safe_basename(name: str) -> str:
    base = PurePosixPath(name.replace("\\", "/")).name.strip()
    if not base or base in (".", ".."):
        raise ValueError("无效文件名")
    if "/" in base or ".." in base:
        raise ValueError("无效文件名")
    return base


def _file_rel(directory: str, filename: str) -> str:
    """非 Markdown：directory/filename（不再使用 attachments/ 子目录）。"""
    d = normalize_directory(directory)
    fn = _safe_basename(filename)
    return f"{d}/{fn}" if d else fn


class KnowledgeWriter:
    """知识库落盘、索引与 changelog 的唯一 seam（Markdown 文档与文本/附件文件）。"""

    def __init__(
        self,
        repo: KnowledgeRepo,
        indexer: Indexer | None = None,
        *,
        skills_dir: str = "技能",
    ):
        self.repo = repo
        self.indexer = indexer
        self.skills_dir = skills_dir.replace("\\", "/").strip("/") or "技能"

    def persist_document(
        self,
        rel_path: str,
        meta: dict,
        body: str,
        *,
        commit_msg: str,
        changelog_line: str,
    ) -> str:
        from app.engine.skills_dir import require_skill_md_in_skills_dir

        norm = rel_path.replace("\\", "/").lstrip("/")
        if is_memory_projection_path(norm):
            raise ValueError(_MEMORY_FILE_DISABLED_MSG)
        require_skill_md_in_skills_dir(norm, self.skills_dir)
        body = sanitize_markdown_image_srcs_for_storage(body)
        self.repo.write_doc(norm, meta, body, commit_msg=commit_msg)
        if self.indexer is not None:
            self.indexer.reindex_doc(norm, body)
        self.repo.log_change(
            changelog_line,
            commit_msg=f"chore: changelog for {norm}",
        )
        return norm

    def update_document_meta(
        self,
        rel_path: str,
        patch: dict,
        *,
        merge: bool = True,
    ) -> dict:
        """只改结构化元数据，正文不动；经 persist_document 以刷新索引与 changelog。"""
        norm = rel_path.replace("\\", "/").lstrip("/")
        if is_memory_projection_path(norm):
            raise ValueError(_MEMORY_FILE_DISABLED_MSG)
        doc = self.repo.read_doc(norm)
        clean = sanitize_doc_meta(patch)
        if not clean:
            raise ValueError("没有可更新的元数据字段（允许 title/tags/source）")
        if merge:
            new_meta = {**doc.meta, **clean}
        else:
            new_meta = {
                k: v
                for k, v in doc.meta.items()
                if k in ("created", "updated", "conversation_ids")
            }
            new_meta.update(clean)
        self.persist_document(
            norm,
            new_meta,
            doc.body,
            commit_msg=f"meta: {norm}",
            changelog_line=f"更新元数据 {norm}",
        )
        return dict(self.repo.read_doc(norm).meta)

    def save_edit(
        self,
        rel_path: str,
        meta: dict,
        old_body: str,
        new_body: str,
        *,
        affected_start: int,
        affected_end: int,
        commit_msg: str | None = None,
        changelog_line: str | None = None,
    ) -> str:
        from app.engine.skills_dir import require_skill_md_in_skills_dir

        norm = rel_path.replace("\\", "/").lstrip("/")
        require_skill_md_in_skills_dir(norm, self.skills_dir)
        msg = commit_msg or f"edit: {norm}"
        new_body = sanitize_markdown_image_srcs_for_storage(new_body)
        self.repo.write_doc(norm, meta, new_body, commit_msg=msg)
        reindex_mode = "full"
        if self.indexer is not None:
            reindex_mode = self.indexer.reindex_doc_after_edit(
                norm, old_body, new_body, affected_start, affected_end
            )
        self.repo.log_change(
            changelog_line or f"Agent 局部编辑 {norm}",
            commit_msg=f"chore: changelog edit {norm}",
        )
        return reindex_mode

    def index_extracted_text(self, rel_path: str, text: str) -> bool:
        """附件等非 Markdown 主文档的可检索文本入索引。"""
        if not text.strip() or self.indexer is None:
            return False
        self.indexer.reindex_doc(rel_path.replace("\\", "/").lstrip("/"), text)
        return True

    def reindex_markdown_body(self, rel_path: str, body: str) -> None:
        """维护性重建索引：文档已在 git，仅刷新 FTS/向量（不写 changelog）。"""
        if self.indexer is None:
            return
        norm = rel_path.replace("\\", "/").lstrip("/")
        self.indexer.reindex_doc(norm, body)

    def move_document(self, from_path: str, to_directory: str, to_filename: str) -> str:
        from_norm = from_path.replace("\\", "/").lstrip("/")
        to_path = join_kb_path(to_directory, to_filename)
        new_path = self.repo.move_doc(
            from_norm,
            to_path,
            commit_msg=f"move: {from_norm} -> {to_path}",
        )
        if self.indexer is not None:
            try:
                self.indexer.remove_doc(from_norm)
            except Exception:
                pass
            doc = self.repo.read_doc(new_path)
            self.indexer.reindex_doc(new_path, doc.body)
        self.repo.log_change(
            f"移动文档 {from_norm} → {new_path}",
            commit_msg=f"chore: changelog move {new_path}",
        )
        return new_path

    def drop_from_index(self, rel_paths: list[str]) -> None:
        if self.indexer is None:
            return
        for rel in rel_paths:
            if rel.endswith(".md"):
                try:
                    self.indexer.remove_doc(rel)
                except Exception:
                    pass

    def record_deletion(self, deleted_path: str, deleted_files: list[str]) -> None:
        if not deleted_files:
            return
        self.repo.log_change(
            f"删除 {deleted_path}（共 {len(deleted_files)} 个文件）",
            commit_msg=f"chore: changelog for delete {deleted_path}",
        )

    @staticmethod
    def resolve_location(args: dict) -> tuple[str | None, dict | None]:
        if "directory" not in args or "filename" not in args:
            return None, {
                "summary": "缺少 directory 或 filename",
                "sources": [],
                "error": "MISSING_PATH",
                "status": "failed",
            }
        try:
            rel = join_kb_path(str(args.get("directory", "")), str(args["filename"]))
        except KbPathError as e:
            return None, {
                "summary": str(e),
                "sources": [],
                "error": "INVALID_PATH",
                "status": "failed",
            }
        return rel, None

    def read_entry_bytes(self, rel_path: str) -> bytes:
        """读取 KB 文件字节（stage / 工具读侧对称入口）。"""
        norm = rel_path.replace("\\", "/").lstrip("/")
        abs_kb = self.repo.abs_path(norm)
        if not abs_kb.exists() or not abs_kb.is_file():
            raise FileNotFoundError(norm)
        return self.repo.read_bytes(norm)

    def assert_non_md_asset_allowed(self, filename: str, *, allow_binary: bool) -> None:
        """非 Markdown 资产准入。

        Agent/publish 默认：文本白名单 + 图片后缀（含 .svg，与 PNG/JPG 同轨）。
        HTTP 树导入可 allow_binary=True 放行其它二进制。
        """
        fn = _safe_basename(filename)
        if is_markdown_path(fn):
            return
        if allow_binary or is_kb_text_file(fn) or is_image_filename(fn):
            return
        raise ValueError(
            f"不支持的文件类型：{fn}（仅允许 Markdown、文本代码/配置类，或图片扩展名）"
        )

    def import_entry(
        self,
        *,
        directory: str,
        filename: str,
        data: bytes,
        allow_binary: bool = True,
    ) -> dict:
        fn = _safe_basename(filename)
        if is_markdown_path(fn):
            try:
                rel = join_kb_path(directory, fn)
            except KbPathError as e:
                raise ValueError(str(e)) from e
            if self.repo.abs_path(rel).exists():
                raise KbPathExistsError(rel)
            text = data.decode("utf-8", errors="replace")
            meta, body = frontmatter.parse(text)
            if not meta.get("title"):
                meta["title"] = title_from_rel_path(rel)
            meta.setdefault("source", "import")
            self.persist_document(
                rel,
                meta,
                body if body.endswith("\n") else body + "\n",
                commit_msg=f"import: {rel}",
                changelog_line=f"导入 {rel}",
            )
            return {"rel_path": rel, "kind": "markdown", "indexed": True}

        self.assert_non_md_asset_allowed(fn, allow_binary=allow_binary)
        rel = _file_rel(directory, fn)
        abs_p = self.repo.abs_path(rel)
        if abs_p.exists():
            # 同路径同字节：幂等复用（粘贴同图再发常见），避免无意义冲突
            if self.repo.read_bytes(rel) == data:
                extracted = extract_text(abs_p)
                indexed = bool(extracted and extracted.strip())
                return {
                    "rel_path": rel,
                    "kind": "file",
                    "indexed": indexed,
                    "reused": True,
                }
            raise KbPathExistsError(rel)
        self.repo.write_bytes(rel, data, commit_msg=f"import file: {rel}")
        extracted = extract_text(self.repo.abs_path(rel))
        indexed = self.index_extracted_text(rel, extracted)
        self.repo.log_change(
            f"导入文件 {rel}",
            commit_msg=f"chore: changelog import {fn}",
        )
        return {"rel_path": rel, "kind": "file", "indexed": indexed}

    def write_text_file(
        self,
        *,
        directory: str,
        filename: str,
        content: str,
        overwrite: bool = False,
    ) -> dict:
        """写入白名单文本资产（非 Markdown）或 SVG；不做 LLM 合并。"""
        fn = _safe_basename(filename)
        if is_markdown_path(fn):
            raise ValueError("Markdown 请使用 write_doc，勿用 write_kb_file")
        # 位图是二进制：Agent 用 generate_image / publish_from_sandbox；此处仅 SVG（UTF-8 文本）
        suffix = PurePosixPath(fn).suffix.lower()
        if is_image_filename(fn) and suffix != ".svg":
            raise ValueError(
                f"位图请用 generate_image 或 publish_from_sandbox，勿用 write_kb_file：{fn}"
            )
        self.assert_non_md_asset_allowed(fn, allow_binary=False)
        rel = _file_rel(directory, fn)
        if not self.repo.is_writable(rel):
            raise ValueError(f"禁止写入：{rel}")
        exists = self.repo.abs_path(rel).exists()
        if exists and not overwrite:
            raise KbPathExistsError(rel)
        data = content.encode("utf-8")
        action = "覆盖" if exists else "写入"
        self.repo.write_bytes(rel, data, commit_msg=f"{action} file: {rel}")
        extracted = extract_text(self.repo.abs_path(rel))
        indexed = self.index_extracted_text(rel, extracted)
        self.repo.log_change(
            f"{action}文件 {rel}",
            commit_msg=f"chore: changelog {action} {fn}",
        )
        return {
            "rel_path": rel,
            "kind": "file",
            "indexed": indexed,
            "overwritten": exists,
        }

    def move_directory_entry(
        self,
        *,
        from_path: str,
        to_directory: str,
        to_name: str | None = None,
    ) -> str:
        from_norm = from_path.replace("\\", "/").strip("/")
        if not from_norm:
            raise ValueError("不能移动根目录")
        name = _safe_basename(to_name or PurePosixPath(from_norm).name)
        try:
            new_root = join_kb_directory(to_directory, name)
        except KbPathError as e:
            raise ValueError(str(e)) from e
        if new_root == from_norm or new_root.startswith(f"{from_norm}/"):
            raise ValueError("不能移动到自身或其子目录内")
        to_dir_norm = to_directory.replace("\\", "/").strip("/")
        if to_dir_norm == from_norm or to_dir_norm.startswith(f"{from_norm}/"):
            raise ValueError("不能移动到自身或其子目录内")
        if self.repo.abs_path(new_root).exists():
            raise KbPathExistsError(new_root)

        from app.engine.skills_dir import is_skill_md_path, require_skill_md_in_skills_dir

        for rel in self.repo.list_tree():
            if rel != from_norm and not rel.startswith(f"{from_norm}/"):
                continue
            if not is_skill_md_path(rel):
                continue
            suffix = rel[len(from_norm) :].lstrip("/")
            new_rel = f"{new_root}/{suffix}" if suffix else f"{new_root}/{PurePosixPath(rel).name}"
            require_skill_md_in_skills_dir(new_rel, self.skills_dir)

        old_paths, new_paths = self.repo.move_directory(
            from_norm,
            new_root,
            commit_msg=f"move dir: {from_norm} -> {new_root}",
        )
        if not old_paths:
            raise FileNotFoundError(from_path)

        self.drop_from_index(old_paths)
        for new in new_paths:
            if is_markdown_path(new):
                doc = self.repo.read_doc(new)
                if self.indexer is not None:
                    self.indexer.reindex_doc(new, doc.body)
            else:
                extracted = extract_text(self.repo.abs_path(new))
                self.index_extracted_text(new, extracted)
        self.repo.log_change(
            f"移动文件夹 {from_norm} → {new_root}（{len(new_paths)} 个文件）",
            commit_msg=f"chore: changelog move dir {new_root}",
        )
        return new_root

    def move_entry(
        self,
        *,
        from_path: str,
        to_directory: str,
        to_filename: str | None = None,
    ) -> str:
        from_norm = from_path.replace("\\", "/").lstrip("/")
        if self.repo.is_protected(from_norm):
            raise ValueError(f"禁止移动：{from_path}")

        from_abs = self.repo.abs_path(from_norm)
        if from_abs.is_dir():
            return self.move_directory_entry(
                from_path=from_norm,
                to_directory=to_directory,
                to_name=to_filename,
            )

        if is_markdown_path(from_norm):
            fn = to_filename or PurePosixPath(from_norm).name
            try:
                rel = join_kb_path(to_directory, fn)
            except KbPathError as e:
                raise ValueError(str(e)) from e
            if self.repo.abs_path(rel).exists():
                raise KbPathExistsError(rel)
            from app.engine.skills_dir import require_skill_md_in_skills_dir

            require_skill_md_in_skills_dir(rel, self.skills_dir)
            try:
                return self.move_document(from_norm, to_directory, fn)
            except ValueError as e:
                if "已存在" in str(e):
                    raise KbPathExistsError(rel) from e
                raise

        fn = _safe_basename(to_filename or PurePosixPath(from_norm).name)
        to_rel = _file_rel(to_directory, fn)
        if self.repo.abs_path(to_rel).exists():
            raise KbPathExistsError(to_rel)
        new_path = self.repo.move_file(
            from_norm, to_rel, commit_msg=f"move: {from_norm} -> {to_rel}"
        )
        self.drop_from_index([from_norm])
        extracted = extract_text(self.repo.abs_path(new_path))
        self.index_extracted_text(new_path, extracted)
        self.repo.log_change(
            f"移动文件 {from_norm} → {new_path}",
            commit_msg=f"chore: changelog move {new_path}",
        )
        return new_path

    def delete_entry(self, path: str) -> list[str]:
        norm = path.replace("\\", "/").rstrip("/")
        if self.repo.is_protected(norm):
            raise ValueError(f"禁止删除：{path}")
        deleted = self.repo.delete_path(norm, commit_msg=f"delete: {norm}")
        if deleted:
            self.drop_from_index(deleted)
            self.record_deletion(norm, deleted)
        return deleted

    def apply_placement(
        self,
        decision: PlacementDecision,
        content: str,
        *,
        write_mode: WriteMode = "merge",
        conversation_id: str | None = None,
        reorganize_existing: Callable[[str, str, str], str] | None = None,
        meta_overrides: dict | None = None,
    ) -> None:
        """按 PlacementDecision 落盘（replace / merge / new）。"""
        rel_path = decision.rel_path
        exists = False
        try:
            self.repo.read_doc(rel_path)
            exists = True
        except FileNotFoundError:
            exists = False

        body = content if content.endswith("\n") else f"{content}\n"
        overrides = sanitize_doc_meta(meta_overrides)

        if write_mode == "replace" and exists:
            doc = self.repo.read_doc(rel_path)
            meta = {
                **doc.meta,
                "title": decision.title or doc.meta.get("title", ""),
            }
            if decision.tags:
                existing_tags = doc.meta.get("tags") or []
                meta["tags"] = list(dict.fromkeys(existing_tags + decision.tags))
            meta = {**meta, **overrides}
            meta = _conversation_ids_meta(meta, conversation_id)
            self.persist_document(
                rel_path,
                meta,
                body,
                commit_msg=f"replace: {rel_path}",
                changelog_line=f"覆盖写入 {rel_path}：{decision.reason or decision.title}",
            )
            return

        if write_mode == "merge" and decision.action in ("merge", "append") and exists:
            if reorganize_existing is None:
                raise ValueError("merge 需要 reorganize_existing")
            doc = self.repo.read_doc(rel_path)
            merged_meta = {
                **doc.meta,
                "title": decision.title or doc.meta.get("title", ""),
            }
            if decision.tags:
                existing_tags = doc.meta.get("tags") or []
                merged_meta["tags"] = list(
                    dict.fromkeys(existing_tags + decision.tags)
                )
            merged_meta = {**merged_meta, **overrides}
            merged_meta = _conversation_ids_meta(merged_meta, conversation_id)
            merged_body = reorganize_existing(doc.body, content, decision.title)
            self.persist_document(
                rel_path,
                merged_meta,
                merged_body,
                commit_msg=f"merge: 整理合并 {rel_path}",
                changelog_line=f"整理合并到 {rel_path}：{decision.reason or decision.title}",
            )
            return

        meta: dict = {
            "title": decision.title,
            "tags": decision.tags,
            "source": "conversation" if conversation_id else "chat",
        }
        meta = {**meta, **overrides}
        meta = _conversation_ids_meta(meta, conversation_id)
        self.persist_document(
            rel_path,
            meta,
            body,
            commit_msg=f"add: 新建 {rel_path}",
            changelog_line=f"创建 {rel_path}：{decision.reason or decision.title}",
        )


_META_READONLY = frozenset({"created", "updated"})
_META_ALLOWED = frozenset({"title", "tags", "source"})


def sanitize_doc_meta(meta: dict | None) -> dict:
    if not meta:
        return {}
    out: dict = {}
    for key, val in meta.items():
        if key in _META_READONLY or key not in _META_ALLOWED:
            continue
        if key == "tags":
            if isinstance(val, list):
                out["tags"] = [str(x) for x in val]
            continue
        if val is None:
            continue
        out[key] = str(val)
    return out


def _conversation_ids_meta(meta: dict, conversation_id: str | None) -> dict:
    if not conversation_id:
        return meta
    existing = meta.get("conversation_ids")
    if isinstance(existing, list):
        ids = list(dict.fromkeys([*existing, conversation_id]))
    else:
        legacy = meta.get("conversation_id")
        ids = list(dict.fromkeys([x for x in (legacy, conversation_id) if x]))
    meta = {k: v for k, v in meta.items() if k not in ("conversation_id",)}
    meta["conversation_ids"] = ids
    meta["source"] = "conversation"
    return meta
