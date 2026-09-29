"""人设修订历史与回退。"""

from __future__ import annotations

from app.engine.memory.cards import KnowledgeCards, parse_scope
from app.engine.roles import RoleStore
from app.engine.text_merge3 import merge3


class PersonaRollbackError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def revision_can_rollback(rev: dict, *, has_earlier_revision: bool) -> bool:
    if rev.get("rolled_back_by"):
        return False
    src = rev.get("source") or ""
    return has_earlier_revision or src not in ("baseline", "create")


class PersonaHistory:
    def __init__(self, roles: RoleStore, cards: KnowledgeCards):
        self.roles = roles
        self.cards = cards

    def list(self, scope: str, *, limit: int = 30) -> list[dict]:
        kind, sid = parse_scope(scope)
        lim = max(1, int(limit))
        rows = self.roles.list_persona_revisions(kind, sid, limit=lim + 1)
        out: list[dict] = []
        for i, rev in enumerate(rows[:lim]):
            prev = rows[i + 1] if i + 1 < len(rows) else None
            previous_body = prev["body"] if prev else ""
            has_earlier = prev is not None
            item = {
                "id": rev["id"],
                "source": rev.get("source") or "",
                "created_at": rev["created_at"],
                "body": rev["body"],
                "previous_body": previous_body,
                "rolled_back": bool(rev.get("rolled_back_by")),
                "can_rollback": revision_can_rollback(
                    rev, has_earlier_revision=has_earlier
                ),
                "reasons": self._reasons(rev),
                "reverts": self._reverts_enriched(rev),
            }
            out.append(item)
        return out

    def _reverts_enriched(self, rev: dict) -> dict | None:
        raw = self._reverts(rev)
        if not raw or not raw.get("id"):
            return None
        target = self.roles.get_persona_revision(raw["id"])
        if not target:
            return None
        return {
            "id": target["id"],
            "source": target.get("source"),
            "created_at": target.get("created_at"),
        }

    def rollback(self, scope: str, revision_id: str) -> dict:
        kind, sid = parse_scope(scope)
        rev = self.roles.get_persona_revision(revision_id)
        if rev is None or rev["subject_kind"] != kind or rev["subject_id"] != sid:
            raise PersonaRollbackError("not_found", "修订不存在")

        if rev.get("rolled_back_by"):
            raise PersonaRollbackError("invalid", "这次改动已经回退过")

        prev_rev = self.roles.previous_persona_revision(revision_id)
        has_earlier = prev_rev is not None
        if not revision_can_rollback(rev, has_earlier_revision=has_earlier):
            raise PersonaRollbackError("invalid", "初始版本不能回退")

        parent = prev_rev["body"] if prev_rev else ""
        current = self.roles.get_persona_body(kind, sid)
        m = merge3(base=rev["body"], ours=current, theirs=parent)
        if not m.clean:
            raise PersonaRollbackError(
                "conflict",
                "这次改动之后，人设的同一处又改过，无法自动回退。请在角色设置里直接修改人设。",
            )

        new_rev = self.roles.rollback_persona_revision(
            kind,
            sid,
            revision_id=revision_id,
            expected_body=current,
            new_body=m.text,
        )
        if new_rev is None:
            raise PersonaRollbackError(
                "changed", "人设刚被修改过，请刷新后再试。"
            )

        if rev.get("source") == "evolution":
            self.cards.persona_state.reject_revision(scope, revision_id)

        self.cards.growth.append(
            scope,
            "persona",
            [
                {
                    "action": "rolled_back",
                    "revision_id": revision_id,
                    "rollback_revision_id": new_rev["id"],
                    "source": rev.get("source"),
                }
            ],
        )

        list_row = self._revision_list_row(new_rev, current)
        return {"ok": True, "revision": list_row, "body": m.text}

    @staticmethod
    def _reasons(rev: dict) -> list[dict]:
        if rev.get("source") != "evolution":
            return []
        meta = rev.get("meta") or {}
        ops = meta.get("ops") or []
        out: list[dict] = []
        for op in ops:
            if not isinstance(op, dict):
                continue
            kind = op.get("op") or ""
            find = str(op.get("find") or "")
            text = str(op.get("text") or "")
            if kind == "replace":
                before, after = find, text
            elif kind == "insert":
                before, after = "", text
            elif kind == "delete":
                before, after = find, ""
            else:
                continue
            basis_items = op.get("basis") or []
            basis: list[str] = []
            for b in basis_items:
                if isinstance(b, dict):
                    stmt = b.get("statement")
                    if stmt:
                        basis.append(str(stmt))
            out.append(
                {
                    "op": kind,
                    "reason": str(op.get("reason") or ""),
                    "before": before,
                    "after": after,
                    "basis": basis,
                }
            )
        return out

    @staticmethod
    def _reverts(rev: dict) -> dict | None:
        if rev.get("source") != "rollback":
            return None
        meta = rev.get("meta") or {}
        target_id = meta.get("reverts")
        if not target_id:
            return None
        return {
            "id": target_id,
            "source": meta.get("reverted_source"),
            "created_at": None,
        }

    def _revision_list_row(self, rev: dict, previous_body: str) -> dict:
        prev = self.roles.previous_persona_revision(rev["id"])
        has_earlier = prev is not None
        return {
            "id": rev["id"],
            "source": rev.get("source") or "",
            "created_at": rev["created_at"],
            "body": rev["body"],
            "previous_body": previous_body,
            "rolled_back": bool(rev.get("rolled_back_by")),
            "can_rollback": revision_can_rollback(
                rev, has_earlier_revision=has_earlier
            ),
            "reasons": self._reasons(rev),
            "reverts": self._reverts_enriched(rev),
        }
