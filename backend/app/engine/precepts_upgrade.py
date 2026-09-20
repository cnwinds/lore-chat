"""官方《戒律》升级：祖先快照 + 三路合并；冲突不写进活文件，待用户确认。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.text_merge3 import ConflictHunk, has_conflict_markers, merge3
from app.engine.agent import system_layer as sl
from app.storage.repo import KnowledgeRepo
from app.time import now_iso_seconds

if TYPE_CHECKING:
    from app.engine.agent.system_layer import SystemLayer
    from app.models.llm import LLMClient

_log = logging.getLogger(__name__)

STOCK_REL = ".kb/precepts/stock.md"
STATE_REL = ".kb/precepts/state.json"

_RESOLVE_SYSTEM = (
    "你在做《戒律》的三路合并收尾：祖先是上次已同步的官方稿，"
    "一边是用户或助手在本地演化的现行戒律，一边是新的官方稿。\n\n"
    "职责：只填冲突块，产出完整合并正文。\n\n"
    "原则：\n"
    "1. 非冲突段落必须与已自动合并的文本一致，不得改写、换序或润色。\n"
    "2. 冲突处若两边仍成立的硬规则能够并存，就都保留，用同一套标题层级收进正文。\n"
    "3. 不得为消冲突而削弱、删节或改写成更松的通项。\n"
    "4. 不能并存时，保留更具体、约束更硬的表述，并吸收另一边仍成立的限定。\n"
    "5. 禁止输出冲突标记（<<<<<<< / ======= / >>>>>>> / |||||||）。\n"
    "6. 只输出完整 Markdown 正文，不要解释、不要代码围栏。"
)


@dataclass
class UpgradeStatus:
    status: str
    path: str
    pending: dict | None
    applied: bool = False
    message: str = ""

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "path": self.path,
            "pending": self.pending,
            "applied": self.applied,
            "message": self.message,
        }


class PreceptsUpgrade:
    """官方《戒律》与本地修订的唯一升级 seam。活文件写入只走 KnowledgeWriter。"""

    def __init__(
        self,
        repo: KnowledgeRepo,
        writer: KnowledgeWriter,
        system_layer: SystemLayer,
        llm: LLMClient | None = None,
    ) -> None:
        self.repo = repo
        self.writer = writer
        self.system_layer = system_layer
        self.llm = llm

    @property
    def path(self) -> str:
        return self.system_layer.precepts_rel

    def _stock_path(self) -> Path:
        return self.repo.root / STOCK_REL

    def _state_path(self) -> Path:
        return self.repo.root / STATE_REL

    def _official(self) -> str:
        return sl._PRECEPTS_BODY

    def _official_hash(self) -> str:
        return sl._seed_hash(self._official())

    def _read_stock(self) -> str | None:
        p = self._stock_path()
        if not p.is_file():
            return None
        text = p.read_text(encoding="utf-8")
        return text if text.strip() else None

    def _write_stock(self, official: str) -> None:
        p = self._stock_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(official, encoding="utf-8")

    def _read_state(self) -> dict:
        p = self._state_path()
        if not p.is_file():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_state(self, data: dict) -> None:
        p = self._state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _read_live(self) -> str | None:
        try:
            return self.repo.read_doc(self.path).body
        except FileNotFoundError:
            return None

    def _write_live(self, body: str, *, commit_msg: str, changelog_line: str) -> None:
        try:
            meta = dict(self.repo.read_doc(self.path).meta)
        except FileNotFoundError:
            meta = {"title": "戒律 · 行为规约", "source": "system"}
        meta.setdefault("title", "戒律 · 行为规约")
        meta["source"] = "system"
        self.writer.persist_document(
            self.path,
            meta,
            body,
            commit_msg=commit_msg,
            changelog_line=changelog_line,
        )
        self.system_layer.invalidate(self.path)

    def _pending_dict(
        self,
        *,
        ours: str,
        theirs: str,
        base: str,
        proposed: str,
        proposed_source: str,
        conflicts: list[ConflictHunk] | list[dict],
        official_hash: str,
        created_at: str | None = None,
        marked: str = "",
    ) -> dict:
        hunks = []
        for item in conflicts:
            if isinstance(item, ConflictHunk):
                hunks.append(item.as_dict())
            else:
                hunks.append(
                    {
                        "base": item.get("base", ""),
                        "ours": item.get("ours", ""),
                        "theirs": item.get("theirs", ""),
                    }
                )
        return {
            "official_hash": official_hash,
            "ours": ours,
            "theirs": theirs,
            "base": base,
            "proposed": proposed,
            "proposed_source": proposed_source,
            "conflicts": hunks,
            "marked": marked,
            "created_at": created_at or now_iso_seconds(),
        }

    def pending_review_path(self) -> str | None:
        """只读：有待用户确认的戒律更新时返回活文件路径，不跑 sync。"""
        pending = self._read_state().get("pending")
        if isinstance(pending, dict) and pending.get("official_hash"):
            return self.path
        return None

    def _last_official_snapshot(self) -> str | None:
        """stock 文件缺失时，从 git 历史找回最近一次仍是官方播种稿的正文。"""
        try:
            revs = self.repo.list_revisions(self.path, limit=80)
        except Exception:
            _log.exception("list precepts revisions for stock recovery failed")
            return None
        for rev in revs:
            try:
                data = self.repo.read_revision(self.path, rev["sha"])
            except Exception:
                continue
            if data.get("binary") or not isinstance(data.get("text"), str):
                continue
            body = data["text"]
            if sl.is_unmodified_official(body):
                return body
        return None

    def _pending_is_reusable(
        self, pending: dict | None, *, official_hash: str, live_hash: str
    ) -> bool:
        if not isinstance(pending, dict):
            return False
        if pending.get("official_hash") != official_hash:
            return False
        if sl._seed_hash(pending.get("ours", "")) != live_hash:
            return False
        # 无祖先的整篇对照可在找回 stock 后重算
        if not str(pending.get("base") or "").strip():
            return False
        # 缺 marked 的旧待确认要重算，合并界面才能按块对照
        if pending.get("conflicts") and not str(pending.get("marked") or "").strip():
            return False
        return True

    def _status_from_state(
        self, *, applied: bool = False, message: str = ""
    ) -> UpgradeStatus:
        pending = self._read_state().get("pending")
        if isinstance(pending, dict) and pending.get("official_hash"):
            return UpgradeStatus(
                status="pending_review",
                path=self.path,
                pending=pending,
                applied=applied,
                message=message,
            )
        return UpgradeStatus(
            status="applied" if applied else "current",
            path=self.path,
            pending=None,
            applied=applied,
            message=message,
        )

    def status(self) -> UpgradeStatus:
        try:
            return self.sync()
        except Exception:
            _log.exception("precepts upgrade sync failed")
            return self._status_from_state(message="同步失败，仍可读当前戒律")

    def sync(self) -> UpgradeStatus:
        self.system_layer.ensure_seeded()
        live = self._read_live()
        if live is None:
            return UpgradeStatus("current", self.path, None, message="尚无戒律")

        official = self._official()
        official_hash = self._official_hash()
        live_hash = sl._seed_hash(live)
        state = self._read_state()
        pending = state.get("pending") if isinstance(state.get("pending"), dict) else None
        skipped = state.get("skipped_official_hash")
        stock = self._read_stock()

        if self._pending_is_reusable(
            pending, official_hash=official_hash, live_hash=live_hash
        ):
            return self._status_from_state()

        if live_hash == official_hash:
            self._write_stock(official)
            if pending or skipped:
                self._write_state({})
            elif stock is None:
                self._write_stock(official)
            return UpgradeStatus("current", self.path, None)

        if skipped == official_hash and not pending:
            if stock is None and sl.is_unmodified_official(live):
                pass
            else:
                return UpgradeStatus("current", self.path, None)

        if stock is None:
            if sl.is_unmodified_official(live):
                self._write_live(
                    official,
                    commit_msg="refresh stock precepts",
                    changelog_line="官方《戒律》已更新",
                )
                self._write_stock(official)
                self._write_state({})
                return UpgradeStatus(
                    "applied",
                    self.path,
                    None,
                    applied=True,
                    message="未改过的官方稿已刷新",
                )
            recovered = self._last_official_snapshot()
            if recovered:
                self._write_stock(recovered)
                stock = recovered
            else:
                merged = merge3("", live, official)
                return self._store_pending(
                    ours=live,
                    theirs=official,
                    base="",
                    result=merged,
                    official_hash=official_hash,
                    message="没有上次官方快照，请确认与新官方稿的差异",
                )

        if sl._seed_hash(stock) == official_hash:
            return UpgradeStatus("current", self.path, None)

        merged = merge3(stock, live, official)
        if merged.clean:
            if sl._seed_hash(merged.text) != live_hash:
                self._write_live(
                    merged.text,
                    commit_msg="merge official precepts",
                    changelog_line="官方《戒律》已与本地修订自动合并",
                )
            self._write_stock(official)
            self._write_state({})
            return UpgradeStatus(
                "applied",
                self.path,
                None,
                applied=True,
                message="官方《戒律》已自动合并",
            )
        return self._store_pending(
            ours=live,
            theirs=official,
            base=stock,
            result=merged,
            official_hash=official_hash,
            message="官方《戒律》与本地修订有冲突，请确认合并稿",
        )

    def _store_pending(
        self,
        *,
        ours: str,
        theirs: str,
        base: str,
        result,
        official_hash: str,
        message: str,
    ) -> UpgradeStatus:
        pending = self._pending_dict(
            ours=ours,
            theirs=theirs,
            base=base,
            proposed=result.text,
            proposed_source="fallback",
            conflicts=result.conflicts,
            official_hash=official_hash,
            marked=result.marked,
        )
        state = self._read_state()
        state["pending"] = pending
        state.pop("skipped_official_hash", None)
        self._write_state(state)
        return UpgradeStatus(
            "pending_review",
            self.path,
            pending,
            message=message,
        )

    def propose(self) -> UpgradeStatus:
        st = self.sync()
        pending = st.pending
        if not pending:
            return st
        if pending.get("proposed_source") == "ai" and pending.get("proposed"):
            return st
        if self.llm is None:
            return st
        proposed = self._resolve_with_llm(pending)
        if not proposed:
            return st
        pending = dict(pending)
        pending["proposed"] = proposed
        pending["proposed_source"] = "ai"
        state = self._read_state()
        state["pending"] = pending
        self._write_state(state)
        return UpgradeStatus(
            "pending_review",
            self.path,
            pending,
            message="已生成合并稿",
        )

    def _resolve_with_llm(self, pending: dict) -> str | None:
        hunks = pending.get("conflicts") or []
        parts = []
        for i, h in enumerate(hunks, start=1):
            parts.append(
                f"--- 冲突 {i} ---\n"
                f"【上次官方】\n{h.get('base', '')}\n"
                f"【当前】\n{h.get('ours', '')}\n"
                f"【新官方】\n{h.get('theirs', '')}\n"
            )
        user = (
            "下面是三路合并后的全文：冲突处已用标记标出。"
            "请按原则只解决冲突，输出完整正文。\n\n"
            f"{pending.get('marked') or self._marked_from_pending(pending)}\n\n"
            "冲突块对照：\n"
            + "\n".join(parts)
        )
        try:
            raw = self.llm.chat(
                [
                    {"role": "system", "content": _RESOLVE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                big=False,
                temperature=0.0,
            )
        except Exception:
            _log.exception("precepts AI merge failed")
            return None
        text = _strip_fence((raw or "").strip())
        fallback = pending.get("proposed") or pending.get("ours") or ""
        if not text or has_conflict_markers(text):
            return None
        if fallback and len(text) < max(40, int(len(fallback) * 0.5)):
            return None
        return text

    def _marked_from_pending(self, pending: dict) -> str:
        result = merge3(
            pending.get("base") or "",
            pending.get("ours") or "",
            pending.get("theirs") or "",
        )
        return result.marked

    def confirm(self, body: str | None = None) -> UpgradeStatus:
        st = self.sync()
        pending = st.pending
        if not pending:
            raise ValueError("没有待确认的戒律更新")
        text = body if body is not None else pending.get("proposed") or ""
        if not str(text).strip():
            raise ValueError("合并稿为空")
        if has_conflict_markers(text):
            raise ValueError("合并稿含有冲突标记，不能写入现行戒律")
        self._write_live(
            text,
            commit_msg="confirm precepts merge",
            changelog_line="已确认官方《戒律》合并",
        )
        self._write_stock(self._official())
        self._write_state({})
        return UpgradeStatus(
            "applied",
            self.path,
            None,
            applied=True,
            message="已采用合并稿",
        )

    def dismiss(self) -> UpgradeStatus:
        st = self.sync()
        pending = st.pending
        official_hash = (
            pending.get("official_hash") if pending else self._official_hash()
        )
        self._write_state({"skipped_official_hash": official_hash})
        return UpgradeStatus(
            "current",
            self.path,
            None,
            message="已保持现行戒律",
        )

    def use_official(self) -> UpgradeStatus:
        official = self._official()
        self._write_live(
            official,
            commit_msg="apply official precepts",
            changelog_line="已改用官方《戒律》",
        )
        self._write_stock(official)
        self._write_state({})
        return UpgradeStatus(
            "applied",
            self.path,
            None,
            applied=True,
            message="已改用官方稿",
        )


def _strip_fence(text: str) -> str:
    raw = text.strip()
    if not raw.startswith("```"):
        return raw
    lines = raw.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
