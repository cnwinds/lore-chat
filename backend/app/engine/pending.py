from __future__ import annotations

import json
import uuid
from pathlib import Path


class PendingStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create(
        self,
        question: str,
        options: list[dict],
        payload: dict,
        *,
        multi_select: bool = False,
    ) -> str:
        data = self._read()
        qid = uuid.uuid4().hex[:12]
        data[qid] = {
            "id": qid,
            "question": question,
            "options": options,
            "payload": payload,
            "multi_select": multi_select,
            "status": "open",
            "choice": None,
        }
        self._write(data)
        return qid

    def get(self, qid: str) -> dict:
        return self._read()[qid]

    def list_open(self) -> list[dict]:
        return [q for q in self._read().values() if q["status"] == "open"]

    def resolve(self, qid: str, choice: str) -> dict:
        data = self._read()
        data[qid]["status"] = "resolved"
        data[qid]["choice"] = choice
        self._write(data)
        return data[qid]

    def resolve_many(self, qid: str, choices: list[str]) -> dict:
        return self.resolve(qid, ",".join(choices))
