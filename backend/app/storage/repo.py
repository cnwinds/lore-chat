from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from git import Repo

from app.storage import frontmatter
from app.time import DISPLAY_TZ, now_iso_seconds


@dataclass
class Document:
    rel_path: str
    meta: dict
    body: str


class KnowledgeRepo:
    def __init__(self, root: str | Path, *, protected_dirs: tuple[str, ...] = ()):
        self.root = Path(root)
        # 额外保护目录（如系统控制层「系统」），禁止 delete_path 删除
        self.protected_dirs = tuple(
            d.replace("\\", "/").strip("/") for d in protected_dirs if d.strip()
        )
        self.root.mkdir(parents=True, exist_ok=True)
        git_dir = self.root / ".git"
        if git_dir.exists():
            self.repo = Repo(self.root)
        else:
            self.repo = Repo.init(self.root)
        with self.repo.config_writer() as cw:
            if not cw.has_option("user", "email"):
                cw.set_value("user", "email", "kb@localhost")
            if not cw.has_option("user", "name"):
                cw.set_value("user", "name", "knowledge-brain")
        (self.root / ".kb").mkdir(exist_ok=True)

    def _abs(self, rel_path: str) -> Path:
        p = (self.root / rel_path).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError(f"路径越界: {rel_path}")
        return p

    def abs_path(self, rel_path: str) -> Path:
        return self._abs(rel_path)

    def _commit(self, rel_paths: list[str], msg: str) -> None:
        self.repo.index.add(rel_paths)
        self.repo.index.commit(msg)

    def read_doc(self, rel_path: str) -> Document:
        abs_p = self._abs(rel_path)
        if not abs_p.exists():
            raise FileNotFoundError(rel_path)
        meta, body = frontmatter.parse(abs_p.read_text(encoding="utf-8"))
        meta = self._normalize_meta(meta, rel_path)
        return Document(rel_path=rel_path, meta=meta, body=body)

    def _first_commit_time(self, rel_path: str) -> str | None:
        try:
            commits = list(
                self.repo.iter_commits(paths=rel_path, max_count=1, reverse=True)
            )
            if commits:
                return (
                    commits[0]
                    .committed_datetime.astimezone(DISPLAY_TZ)
                    .isoformat(timespec="seconds")
                )
        except Exception:
            return None
        return None

    def _normalize_meta(self, meta: dict, rel_path: str) -> dict:
        if meta.get("created"):
            return meta
        created = meta.get("updated") or self._first_commit_time(rel_path)
        if created:
            return {**meta, "created": created}
        return meta

    def write_doc(
        self, rel_path: str, meta: dict, body: str, *, commit_msg: str
    ) -> None:
        abs_p = self._abs(rel_path)
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        now = now_iso_seconds()
        if abs_p.exists():
            existing_meta, _ = frontmatter.parse(abs_p.read_text(encoding="utf-8"))
            created = (
                existing_meta.get("created")
                or existing_meta.get("updated")
                or now
            )
        else:
            created = meta.get("created") or now
        out_meta = {**meta, "created": created, "updated": now}
        abs_p.write_text(frontmatter.dump(out_meta, body), encoding="utf-8")
        self._commit([rel_path], commit_msg)

    def append_doc(self, rel_path: str, extra_body: str, *, commit_msg: str) -> None:
        doc = self.read_doc(rel_path)
        new_body = doc.body
        if not new_body.endswith("\n"):
            new_body += "\n"
        new_body += extra_body
        self.write_doc(rel_path, doc.meta, new_body, commit_msg=commit_msg)

    def list_tree(self) -> list[str]:
        out: list[str] = []
        for p in sorted(self.root.rglob("*.md")):
            rel = p.relative_to(self.root).as_posix()
            if rel.startswith(".kb/"):
                continue
            out.append(rel)
        return out

    def save_attachment(
        self, rel_dir: str, filename: str, data: bytes, *, commit_msg: str
    ) -> str:
        rel_path = f"{rel_dir.rstrip('/')}/attachments/{filename}"
        abs_p = self._abs(rel_path)
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        abs_p.write_bytes(data)
        self._commit([rel_path], commit_msg)
        return rel_path

    def get_attachment(self, rel_path: str) -> bytes:
        abs_p = self._abs(rel_path)
        if not abs_p.exists():
            raise FileNotFoundError(rel_path)
        return abs_p.read_bytes()

    def _is_internal(self, rel_path: str) -> bool:
        """`.kb/`、`.git/` 等内部路径，禁止读写与删除。"""
        norm = rel_path.replace("\\", "/").lstrip("/")
        return norm == ".kb" or norm.startswith(".kb/") or norm.startswith(".git/")

    def _is_protected(self, rel_path: str) -> bool:
        norm = rel_path.replace("\\", "/").lstrip("/")
        if self._is_internal(norm):
            return True
        for d in self.protected_dirs:
            if norm == d or norm.startswith(d + "/"):
                return True
        return False

    def is_protected(self, rel_path: str) -> bool:
        return self._is_protected(rel_path)

    def is_writable(self, rel_path: str) -> bool:
        return not self._is_internal(rel_path)

    def delete_path(self, rel_path: str, *, commit_msg: str) -> list[str]:
        norm = rel_path.replace("\\", "/").rstrip("/")
        if self._is_protected(norm):
            raise ValueError(f"禁止删除系统目录: {rel_path}")
        abs_p = self._abs(norm)
        if not abs_p.exists():
            raise FileNotFoundError(rel_path)

        if abs_p.is_file():
            if not norm.endswith(".md"):
                raise ValueError(f"只能删除 Markdown 文档: {rel_path}")
            deleted = [norm]
            abs_p.unlink()
        else:
            deleted = []
            for p in sorted(abs_p.rglob("*")):
                if not p.is_file():
                    continue
                rel = p.relative_to(self.root).as_posix()
                if self._is_protected(rel):
                    continue
                deleted.append(rel)
            shutil.rmtree(abs_p)

        if deleted:
            self.repo.index.remove(deleted)
            self.repo.index.commit(commit_msg)
        return deleted

    def move_doc(self, from_path: str, to_path: str, *, commit_msg: str) -> str:
        from_norm = from_path.replace("\\", "/").lstrip("/")
        to_norm = to_path.replace("\\", "/").lstrip("/")
        if from_norm == to_norm:
            return from_norm
        if self._is_protected(from_norm) or self._is_protected(to_norm):
            raise ValueError(f"禁止移动系统或内部路径: {from_path} -> {to_path}")
        if not from_norm.endswith(".md") or not to_norm.endswith(".md"):
            raise ValueError("只能移动 Markdown 文档")
        from_abs = self._abs(from_norm)
        if not from_abs.is_file():
            raise FileNotFoundError(from_path)
        to_abs = self._abs(to_norm)
        if to_abs.exists():
            raise ValueError(f"目标路径已存在：{to_path}")
        doc = self.read_doc(from_norm)
        self.write_doc(to_norm, doc.meta, doc.body, commit_msg=commit_msg)
        from_abs.unlink()
        self.repo.index.remove([from_norm])
        self.repo.index.commit(commit_msg)
        return to_norm

    def log_change(
        self, entry: str, *, commit_msg: str = "chore: update changelog"
    ) -> None:
        path = self.root / ".kb" / "changelog.md"
        stamp = now_iso_seconds()
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- {stamp} {entry}\n")
        self._commit([".kb/changelog.md"], commit_msg)
