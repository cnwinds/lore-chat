from __future__ import annotations

from app.engine.agent.tool_catalog import resolve_kb_location
from app.engine.agent.tool_impl.doc_read_guard import DocReadGuard
from app.engine.conversations import ConversationStore
from app.engine.write_policy import WriteMode
from app.engine.knowledge_writer import (
    KbPathExistsError,
    KnowledgeWriter,
    is_markdown_path,
)
from app.engine.memory.constants import is_memory_projection_path

_MEMORY_FILE_DISABLED_MSG = (
    "记忆已改由数据库管理，请到设置 → 记忆中编辑，或使用 manage_memory"
)
from app.engine.organizer import Organizer
from app.engine.patch import Edit, Insert, apply_edits, apply_insert
from app.storage.kb_media_paths import is_image_filename
from app.storage.kb_paths import KbPathError
from app.storage.repo import KnowledgeRepo


class KbMutateTools:
    def __init__(
        self,
        *,
        repo: KnowledgeRepo,
        organizer: Organizer,
        knowledge_writer: KnowledgeWriter,
        read_guard: DocReadGuard,
        memory_service=None,
        conversations=None,
        system_layer=None,
        edit_doc_max_edits: int = 10,
        edit_doc_max_patch_chars: int = 8192,
    ) -> None:
        self.repo = repo
        self.organizer = organizer
        self.knowledge_writer = knowledge_writer
        self.read_guard = read_guard
        self.memory_service = memory_service
        self.conversations = conversations
        self.system_layer = system_layer
        self.edit_doc_max_edits = edit_doc_max_edits
        self.edit_doc_max_patch_chars = edit_doc_max_patch_chars

    def write_doc(self, args: dict) -> dict:
        rel_path, err = resolve_kb_location(args)
        if err:
            return err
        if is_memory_projection_path(rel_path):
            return {
                "summary": _MEMORY_FILE_DISABLED_MSG,
                "sources": [],
                "error": "memory_file_disabled",
                "status": "failed",
            }
        text = args["text"]
        if args.get("context"):
            text = args["context"] + "\n\n" + text
        mode_raw = args.get("write_mode", "auto")
        write_mode: WriteMode = (
            mode_raw if mode_raw in ("auto", "merge", "replace") else "auto"
        )
        meta = args.get("meta")
        if meta is not None and not isinstance(meta, dict):
            return {
                "summary": "meta 必须是对象（如 {title, tags}）",
                "sources": [],
                "error": "INVALID_META",
                "status": "failed",
            }
        result = self.organizer.ingest_text(
            text,
            forced_rel_path=rel_path,
            write_mode=write_mode,
            meta=meta if isinstance(meta, dict) else None,
        )
        sources = [{"type": "kb", "path": result.rel_path}] if result.rel_path else []
        out: dict = {
            "summary": result.message,
            "sources": sources,
            "ingest_result": result,
            "status": result.status,
            "rel_path": result.rel_path,
        }
        if result.question_id:
            out["question_id"] = result.question_id
        return out

    def _resolve_doc_meta_path(self, args: dict) -> tuple[str | None, dict | None]:
        path = (args.get("path") or "").replace("\\", "/").lstrip("/")
        if not path:
            return None, {
                "summary": "缺少 path",
                "sources": [],
                "error": "MISSING_PATH",
                "status": "failed",
            }
        if is_memory_projection_path(path):
            return None, {
                "summary": _MEMORY_FILE_DISABLED_MSG,
                "sources": [],
                "error": "memory_file_disabled",
                "status": "failed",
            }
        return path, None

    def read_doc_meta(self, args: dict) -> dict:
        path, err = self._resolve_doc_meta_path(args)
        if err:
            return err
        assert path is not None
        try:
            doc = self.repo.read_doc(path)
        except FileNotFoundError:
            return {
                "summary": f"文档不存在：{path}",
                "sources": [],
                "error": "NOT_FOUND",
                "status": "failed",
            }
        except Exception as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": "READ_FAILED",
                "status": "failed",
            }
        return {
            "summary": f"已读取元数据：{path}",
            "sources": [{"type": "kb", "path": path}],
            "path": path,
            "meta": dict(doc.meta),
            "status": "ok",
        }

    def update_doc_meta(self, args: dict) -> dict:
        path, err = self._resolve_doc_meta_path(args)
        if err:
            return err
        assert path is not None
        patch = args.get("meta")
        if not isinstance(patch, dict) or not patch:
            return {
                "summary": "缺少 meta 对象",
                "sources": [],
                "error": "MISSING_META",
                "status": "failed",
            }
        merge = bool(args.get("merge", True))
        try:
            meta = self.knowledge_writer.update_document_meta(
                path, patch, merge=merge
            )
        except FileNotFoundError:
            return {
                "summary": f"文档不存在：{path}",
                "sources": [],
                "error": "NOT_FOUND",
                "status": "failed",
            }
        except ValueError as e:
            return {
                "summary": str(e),
                "sources": [{"type": "kb", "path": path}],
                "error": "EMPTY_META" if "可更新" in str(e) else "WRITE_FAILED",
                "status": "failed",
            }
        except Exception as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": "WRITE_FAILED",
                "status": "failed",
            }
        return {
            "summary": f"已更新元数据：{path}",
            "sources": [{"type": "kb", "path": path}],
            "path": path,
            "meta": meta,
            "status": "ok",
        }

    def write_kb_file(self, args: dict) -> dict:
        directory = args.get("directory")
        filename = (args.get("filename") or "").strip()
        if directory is None or not filename:
            return {
                "summary": "缺少 directory 或 filename",
                "sources": [],
                "error": "MISSING_PATH",
                "status": "failed",
            }
        if "content" not in args:
            return {
                "summary": "缺少 content",
                "sources": [],
                "error": "MISSING_CONTENT",
                "status": "failed",
            }
        content = args["content"]
        if not isinstance(content, str):
            return {
                "summary": "content 必须是字符串",
                "sources": [],
                "error": "INVALID_CONTENT",
                "status": "failed",
            }
        overwrite = bool(args.get("overwrite", False))
        try:
            result = self.knowledge_writer.write_text_file(
                directory=str(directory),
                filename=filename,
                content=content,
                overwrite=overwrite,
            )
        except KbPathExistsError as e:
            return {
                "summary": f"目标已存在：{e.rel_path}（传 overwrite=true 可覆盖）",
                "sources": [],
                "error": "ALREADY_EXISTS",
                "status": "failed",
                "rel_path": e.rel_path,
            }
        except (ValueError, KbPathError) as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": "INVALID",
                "status": "failed",
            }
        rel = result["rel_path"]
        action = "已覆盖" if result.get("overwritten") else "已写入"
        out: dict = {
            "summary": f"{action}知识库文件：{rel}",
            "sources": [{"type": "kb", "path": rel}],
            "status": "saved",
            "rel_path": rel,
            "kind": result.get("kind"),
            "overwritten": bool(result.get("overwritten")),
        }
        # SVG 等图片与 PNG 同轨：挂附件以便信息流出缩略图
        if is_image_filename(filename):
            out["attachments"] = [rel]
        return out

    def summarize_conversation(
        self, args: dict, *, conversation_id: str | None = None
    ) -> dict:
        if not conversation_id or self.conversations is None:
            return {
                "summary": "当前不在具名会话中，无法归档整段会话。",
                "sources": [],
                "error": "no conversation context",
            }
        try:
            conv = self.conversations.get(conversation_id)
        except KeyError:
            return {
                "summary": "会话不存在，无法归档。",
                "sources": [],
                "error": f"conversation not found: {conversation_id}",
            }
        transcript = ConversationStore.full_transcript(conv)
        system_rules = self.system_layer.compose() if self.system_layer else ""
        rel_path, err = resolve_kb_location(args)
        if err:
            return err
        if is_memory_projection_path(rel_path):
            return {
                "summary": _MEMORY_FILE_DISABLED_MSG,
                "sources": [],
                "error": "memory_file_disabled",
                "status": "failed",
            }
        result = self.organizer.summarize_conversation(
            transcript,
            conv=conv,
            forced_rel_path=rel_path,
            system_rules=system_rules,
            conversation_id=conversation_id,
        )
        sources = (
            [{"type": "kb", "path": result.rel_path}] if result.rel_path else []
        )
        if result.status == "saved" and result.rel_path:
            self.conversations.summaries.mark_summarized(
                conversation_id, result.rel_path
            )
        return {"summary": result.message, "sources": sources}

    def move_entry(self, args: dict) -> dict:
        from_path = args.get("from_path", "").replace("\\", "/").lstrip("/")
        if not from_path:
            return {
                "summary": "缺少 from_path",
                "sources": [],
                "error": "MISSING_PATH",
                "status": "failed",
            }
        to_directory = str(args.get("to_directory", ""))
        raw_fn = args.get("to_filename")
        to_filename = (
            str(raw_fn) if raw_fn is not None and str(raw_fn).strip() else None
        )
        try:
            new_path = self.knowledge_writer.move_entry(
                from_path=from_path,
                to_directory=to_directory,
                to_filename=to_filename,
            )
        except FileNotFoundError:
            return {
                "summary": f"源路径不存在：{from_path}",
                "sources": [],
                "error": "NOT_FOUND",
                "status": "failed",
            }
        except KbPathExistsError as e:
            return {
                "summary": f"目标路径已存在：{e}",
                "sources": [],
                "error": "ALREADY_EXISTS",
                "status": "failed",
            }
        except ValueError as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": "PROTECTED_OR_INVALID",
                "status": "failed",
            }
        except KbPathError as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": "INVALID_PATH",
                "status": "failed",
            }
        return {
            "summary": f"已移动 {from_path} → {new_path}",
            "sources": [{"type": "kb", "path": new_path}],
            "status": "saved",
            "rel_path": new_path,
            "from_path": from_path,
        }

    def delete_kb(self, args: dict) -> dict:
        path = args["path"]
        try:
            deleted = self.knowledge_writer.delete_entry(path)
        except FileNotFoundError:
            return {
                "summary": f"路径不存在：{path}",
                "sources": [],
                "error": f"FileNotFoundError: {path}",
            }
        except ValueError as e:
            return {"summary": str(e), "sources": [], "error": str(e)}

        return {
            "summary": f"已删除 {path}（{len(deleted)} 个文件）",
            "sources": [],
            "deleted_paths": deleted,
        }

    def edit_doc(self, args: dict, *, conversation_id: str | None = None) -> dict:
        path = args["path"]
        edits_raw = args.get("edits")
        insert_raw = args.get("insert")

        if edits_raw and insert_raw:
            return self._edit_doc_error("INVALID", "edits 与 insert 不能同时使用")
        if not edits_raw and not insert_raw:
            return self._edit_doc_error("INVALID", "必须提供 edits 或 insert")

        if is_memory_projection_path(path):
            return self._edit_doc_error("MEMORY_FILE_DISABLED", _MEMORY_FILE_DISABLED_MSG)

        if not self.repo.is_writable(path):
            return self._edit_doc_error("PROTECTED", f"路径不可写：{path}")

        if not is_markdown_path(path):
            return self._edit_doc_error(
                "NOT_MARKDOWN",
                f"非 Markdown 请用 write_kb_file(overwrite=true) 整文件覆盖：{path}",
            )

        if not self.read_guard.is_read(conversation_id, path):
            return self._edit_doc_error("NOT_READ", f"请先 read_doc 再编辑：{path}")

        try:
            doc = self.repo.read_doc(path)
        except FileNotFoundError:
            return self._edit_doc_error("NOT_FOUND", f"文档不存在：{path}")

        old_body = doc.body

        if insert_raw:
            if not isinstance(insert_raw, dict):
                return self._edit_doc_error("INVALID", "insert 参数格式无效")
            insert = Insert(
                content=insert_raw.get("content", ""),
                after_heading=insert_raw.get("after_heading"),
                at_offset=insert_raw.get("at_offset"),
            )
            result = apply_insert(
                old_body, insert, max_patch_chars=self.edit_doc_max_patch_chars
            )
        else:
            if len(edits_raw) > self.edit_doc_max_edits:
                return self._edit_doc_error(
                    "TOO_LARGE",
                    f"单次最多 {self.edit_doc_max_edits} 处 edits",
                )
            edits = [
                Edit(
                    old_string=e["old_string"],
                    new_string=e["new_string"],
                    replace_all=bool(e.get("replace_all", False)),
                )
                for e in edits_raw
            ]
            result = apply_edits(
                old_body, edits, max_patch_chars=self.edit_doc_max_patch_chars
            )

        return self._finalize_edit_doc(
            path, doc, old_body, result, conversation_id=conversation_id
        )

    @staticmethod
    def _edit_doc_error(code: str, message: str, **extra) -> dict:
        out = {
            "summary": message,
            "sources": [],
            "status": "failed",
            "error": code,
            **extra,
        }
        if code == "NOT_READ":
            out["suggestion"] = "请先调用 read_doc 读取该文档后再 edit_doc"
        return out

    def _finalize_edit_doc(
        self,
        path: str,
        doc,
        old_body: str,
        result,
        *,
        conversation_id: str | None = None,
    ) -> dict:
        if not result.ok:
            err = result.error
            out = self._edit_doc_error(err.code, result.message)
            if err.hint:
                out["hint"] = err.hint
            if err.occurrences:
                out["occurrences"] = err.occurrences
            if err.suggestion:
                out["suggestion"] = err.suggestion
            return out

        reindex_mode = self.knowledge_writer.save_edit(
            path,
            doc.meta,
            old_body,
            result.body,
            affected_start=result.affected_start,
            affected_end=result.affected_end,
        )
        self.read_guard.mark(conversation_id, path)

        return {
            "summary": f"已在 {path} {result.message}",
            "sources": [{"type": "kb", "path": path}],
            "status": "saved",
            "applied": result.applied,
            "preview": result.preview,
            "reindex_mode": reindex_mode,
        }
