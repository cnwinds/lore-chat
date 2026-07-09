from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from git import Repo

from app.storage import frontmatter


@dataclass
class Document:
    rel_path: str
    meta: dict
    body: str


class KnowledgeRepo:
    def __init__(self, root: str | Path):
        self.root = Path(root)
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

    def _commit(self, rel_paths: list[str], msg: str) -> None:
        self.repo.index.add(rel_paths)
        self.repo.index.commit(msg)

    def read_doc(self, rel_path: str) -> Document:
        abs_p = self._abs(rel_path)
        if not abs_p.exists():
            raise FileNotFoundError(rel_path)
        meta, body = frontmatter.parse(abs_p.read_text(encoding="utf-8"))
        return Document(rel_path=rel_path, meta=meta, body=body)

    def write_doc(
        self, rel_path: str, meta: dict, body: str, *, commit_msg: str
    ) -> None:
        abs_p = self._abs(rel_path)
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        meta = {"updated": datetime.now().isoformat(timespec="seconds"), **meta}
        abs_p.write_text(frontmatter.dump(meta, body), encoding="utf-8")
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

    def log_change(
        self, entry: str, *, commit_msg: str = "chore: update changelog"
    ) -> None:
        path = self.root / ".kb" / "changelog.md"
        stamp = datetime.now().isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- {stamp} {entry}\n")
        self._commit([".kb/changelog.md"], commit_msg)
