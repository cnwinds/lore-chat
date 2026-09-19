from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from git import Blob, Repo

from app.storage import frontmatter
from app.time import DISPLAY_TZ, now_wall_clock

_REV_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_MAX_REVISIONS = 200


def revision_summary(message: str, rel_path: str) -> str:
    """把 git 提交首行收成给用户看的短说明。"""
    line = (message or "").strip().split("\n", 1)[0].strip()
    if line in {f"edit: {rel_path}", f"用户编辑 {rel_path}"}:
        return "编辑"
    if line.startswith("seed system layer:"):
        return "初次写入"
    if line == "refresh stock precepts":
        return "官方稿更新"
    if line == "merge official precepts":
        return "官方稿合并"
    if line == "confirm precepts merge":
        return "确认官方合并"
    if line == "apply official precepts":
        return "采用官方稿"
    return line or "修订"


@dataclass
class Document:
    rel_path: str
    meta: dict
    body: str


def _decode_revision_text(rel_path: str, data: bytes) -> tuple[str | None, bool]:
    if not data:
        return "", False
    if b"\x00" in data:
        return None, True
    try:
        raw = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, True
    if rel_path.endswith(".md"):
        _meta, body = frontmatter.parse(raw)
        return body, False
    return raw, False


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
        now = now_wall_clock()
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
        for p in sorted(self.root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.root).as_posix()
            if rel.startswith(".kb/") or rel.startswith(".git/"):
                continue
            base = p.name
            if base == ".gitkeep":
                continue
            out.append(rel)
        return out

    def write_bytes(self, rel_path: str, data: bytes, *, commit_msg: str) -> str:
        norm = rel_path.replace("\\", "/").lstrip("/")
        if self._is_internal(norm):
            raise ValueError(f"禁止写入：{rel_path}")
        abs_p = self._abs(norm)
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        abs_p.write_bytes(data)
        self._commit([norm], commit_msg)
        return norm

    def write_files(
        self, files: list[tuple[str, bytes]], *, commit_msg: str
    ) -> list[str]:
        """写入多个新文件并一次 commit（Skill 解包等批量导入）。"""
        if not files:
            raise ValueError("没有可写入的文件")
        written: list[str] = []
        for rel_path, data in files:
            norm = rel_path.replace("\\", "/").lstrip("/")
            if self._is_internal(norm):
                raise ValueError(f"禁止写入：{rel_path}")
            abs_p = self._abs(norm)
            if abs_p.exists():
                raise ValueError(f"目标路径已存在：{rel_path}")
            abs_p.parent.mkdir(parents=True, exist_ok=True)
            abs_p.write_bytes(data)
            written.append(norm)
        self._commit(written, commit_msg)
        return written

    def read_bytes(self, rel_path: str) -> bytes:
        abs_p = self._abs(rel_path)
        if not abs_p.exists():
            raise FileNotFoundError(rel_path)
        return abs_p.read_bytes()

    def _norm_user_path(self, rel_path: str) -> str:
        norm = rel_path.replace("\\", "/").lstrip("/")
        if not norm or ".." in PurePosixPath(norm).parts:
            raise ValueError(f"路径越界: {rel_path}")
        if self._is_internal(norm):
            raise PermissionError("禁止访问内部路径")
        self._abs(norm)
        return norm

    def _blob_at(self, commit, rel_path: str) -> Blob | None:
        try:
            item = commit.tree / rel_path
        except KeyError:
            return None
        return item if isinstance(item, Blob) else None

    def list_revisions(self, rel_path: str, *, limit: int = 80) -> list[dict]:
        """某文件内容发生变化的提交，新的在前；连续相同正文会并成一条。"""
        norm = self._norm_user_path(rel_path)
        cap = max(1, min(int(limit), _MAX_REVISIONS))
        exists = self._abs(norm).is_file()
        out: list[dict] = []
        prev_blob: str | None = None
        try:
            commits = self.repo.iter_commits(paths=norm, max_count=cap * 2)
        except Exception:
            commits = []
        for commit in commits:
            blob = self._blob_at(commit, norm)
            if blob is None:
                continue
            if blob.hexsha == prev_blob:
                continue
            prev_blob = blob.hexsha
            out.append(
                {
                    "sha": commit.hexsha,
                    "short_sha": commit.hexsha[:7],
                    "message": revision_summary(commit.message, norm),
                    "committed_at": commit.committed_datetime.astimezone(
                        DISPLAY_TZ
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            if len(out) >= cap:
                break
        if not out and not exists:
            raise FileNotFoundError(rel_path)
        return out

    def read_revision(self, rel_path: str, sha: str) -> dict:
        """读取某次提交里该文件的正文（Markdown 去掉库头）。"""
        norm = self._norm_user_path(rel_path)
        token = (sha or "").strip()
        if not _REV_SHA_RE.fullmatch(token):
            raise ValueError("无效版本")
        try:
            commit = self.repo.commit(token)
        except Exception as exc:
            raise FileNotFoundError(rel_path) from exc
        blob = self._blob_at(commit, norm)
        if blob is None:
            raise FileNotFoundError(rel_path)
        data = blob.data_stream.read()
        text, binary = _decode_revision_text(norm, data)
        return {
            "path": norm,
            "sha": commit.hexsha,
            "short_sha": commit.hexsha[:7],
            "message": revision_summary(commit.message, norm),
            "committed_at": commit.committed_datetime.astimezone(DISPLAY_TZ).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "text": text,
            "binary": binary,
            "size": len(data),
        }

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

    def _dir_has_kb_files(self, abs_dir: Path) -> bool:
        for p in abs_dir.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(self.root).as_posix()
            if rel.startswith(".git/") or rel.startswith(".kb/"):
                continue
            if p.name == ".gitkeep":
                continue
            if self._is_protected(rel):
                continue
            return True
        return False

    def _prune_empty_directories(self, rel_dir: str) -> None:
        """移动/删除文件后，自底向上移除已无知识库文件的目录。"""
        norm = rel_dir.replace("\\", "/").strip("/")
        while norm:
            if self._is_protected(norm):
                break
            abs_p = self._abs(norm)
            if not abs_p.is_dir():
                break
            if self._dir_has_kb_files(abs_p):
                break
            shutil.rmtree(abs_p)
            parent = PurePosixPath(norm).parent.as_posix()
            norm = "" if parent in ("", ".") else parent

    def remove_file(
        self, rel_path: str, *, commit_msg: str, allow_protected: bool = False
    ) -> bool:
        """删除单个已跟踪/未跟踪文件并尽量 git commit。用于系统层遗留文件清理。"""
        norm = rel_path.replace("\\", "/").lstrip("/")
        if self._is_internal(norm):
            raise ValueError(f"禁止删除内部路径: {rel_path}")
        if self._is_protected(norm) and not allow_protected:
            raise ValueError(f"禁止删除: {rel_path}")
        abs_p = self._abs(norm)
        if not abs_p.exists() or not abs_p.is_file():
            return False
        abs_p.unlink()
        try:
            self.repo.index.remove([norm])
            self.repo.index.commit(commit_msg)
        except Exception:
            # 未跟踪文件：工作区已删即可
            pass
        parent = PurePosixPath(norm).parent.as_posix()
        if parent not in ("", "."):
            self._prune_empty_directories(parent)
        return True

    def delete_path(self, rel_path: str, *, commit_msg: str) -> list[str]:
        norm = rel_path.replace("\\", "/").rstrip("/")
        if self._is_protected(norm):
            raise ValueError(f"禁止删除系统目录: {rel_path}")
        abs_p = self._abs(norm)
        if not abs_p.exists():
            raise FileNotFoundError(rel_path)

        if abs_p.is_file():
            if self._is_protected(norm):
                raise ValueError(f"禁止删除: {rel_path}")
            deleted = [norm]
            abs_p.unlink()
            parent = PurePosixPath(norm).parent.as_posix()
            if parent not in ("", "."):
                self._prune_empty_directories(parent)
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
        parent = PurePosixPath(from_norm).parent.as_posix()
        if parent not in ("", "."):
            self._prune_empty_directories(parent)
        self.repo.index.remove([from_norm])
        self.repo.index.commit(commit_msg)
        return to_norm

    def move_file(self, from_path: str, to_path: str, *, commit_msg: str) -> str:
        from_norm = from_path.replace("\\", "/").lstrip("/")
        to_norm = to_path.replace("\\", "/").lstrip("/")
        if from_norm == to_norm:
            return from_norm
        if self._is_protected(from_norm) or self._is_protected(to_norm):
            raise ValueError(f"禁止移动: {from_path} -> {to_path}")
        from_abs = self._abs(from_norm)
        if not from_abs.is_file():
            raise FileNotFoundError(from_path)
        to_abs = self._abs(to_norm)
        if to_abs.exists():
            raise ValueError(f"目标路径已存在：{to_path}")
        to_abs.parent.mkdir(parents=True, exist_ok=True)
        from_abs.rename(to_abs)
        parent = PurePosixPath(from_norm).parent.as_posix()
        if parent not in ("", "."):
            self._prune_empty_directories(parent)
        # 源可能未跟踪（list_tree 含工作区文件）；remove 失败仍须 add 目标
        try:
            self.repo.index.remove([from_norm])
        except Exception:
            pass
        self.repo.index.add([to_norm])
        self.repo.index.commit(commit_msg)
        return to_norm

    def move_directory(self, from_dir: str, to_dir: str, *, commit_msg: str) -> tuple[list[str], list[str]]:
        from_norm = from_dir.replace("\\", "/").strip("/")
        to_norm = to_dir.replace("\\", "/").strip("/")
        if not from_norm:
            raise ValueError("不能移动根目录")
        if from_norm == to_norm:
            return [], []
        if self._is_protected(from_norm) or self._is_protected(to_norm):
            raise ValueError(f"禁止移动: {from_dir} -> {to_dir}")
        from_abs = self._abs(from_norm)
        if not from_abs.exists():
            raise FileNotFoundError(from_dir)
        if not from_abs.is_dir():
            raise ValueError(f"不是目录: {from_dir}")

        to_abs = self._abs(to_norm)
        if to_abs.exists():
            raise ValueError(f"目标路径已存在：{to_dir}")

        old_paths: list[str] = []
        for p in sorted(from_abs.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.root).as_posix()
            if not self._is_protected(rel):
                old_paths.append(rel)

        to_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(from_abs), str(to_abs))
        parent = PurePosixPath(from_norm).parent.as_posix()
        if parent not in ("", "."):
            self._prune_empty_directories(parent)

        prefix_old = from_norm + "/"
        prefix_new = to_norm + "/"
        new_paths: list[str] = []
        for old in old_paths:
            if old.startswith(prefix_old):
                new_paths.append(prefix_new + old[len(prefix_old) :])
            else:
                new_paths.append(to_norm)

        if old_paths:
            self.repo.index.remove(old_paths)
            self.repo.index.add(new_paths)
            self.repo.index.commit(commit_msg)
        return old_paths, new_paths

    def log_change(
        self, entry: str, *, commit_msg: str = "chore: update changelog"
    ) -> None:
        path = self.root / ".kb" / "changelog.md"
        stamp = now_wall_clock()
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- {stamp} {entry}\n")
        self._commit([".kb/changelog.md"], commit_msg)
