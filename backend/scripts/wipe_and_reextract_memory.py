"""一次性：清空记忆事实并以 immediate 全量重抽全部会话。

用法（容器内）:
  PYTHONPATH=/app python /app/scripts/wipe_and_reextract_memory.py

mark_dirty 不传 at，不会改侧栏 updated_at / last_user_message_at。
入队前会先 repair 活跃时间，修复历史污染。
"""

from __future__ import annotations

import time

from app.deps import build_container
from app.engine.conversation.activity_times import repair_activity_times
from app.settings_store import load_effective_settings


def main() -> None:
    settings = load_effective_settings()
    key = (settings.openai_api_key or "").strip()
    if key in {"", "sk-none", "sk-your-key"}:
        raise SystemExit("OPENAI_API_KEY 仍为占位符，拒绝重抽")
    c = build_container(settings)
    store = c.memory_service.store
    conv = c.conversations
    worker = c.memory_worker

    with store._connect() as conn:
        before_facts = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        before_ev = conn.execute("SELECT COUNT(*) FROM memory_evidence").fetchone()[0]
        before_ts = conn.execute("SELECT COUNT(*) FROM memory_tombstones").fetchone()[0]
        conn.execute("DELETE FROM memory_evidence")
        conn.execute("DELETE FROM memory_facts")
        conn.execute("DELETE FROM memory_tombstones")
        conn.execute(
            """
            UPDATE memory_render_state
            SET revision = 0,
                file_hash = NULL,
                file_mtime = NULL,
                rendered_fact_ids_json = '[]',
                valid_snapshot_body = NULL,
                render_dirty = 1,
                git_dirty = 0
            """
        )
        conn.commit()
        after_facts = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]

    print(
        f"wiped facts={before_facts}->{after_facts} "
        f"evidence={before_ev} tombstones={before_ts}",
        flush=True,
    )

    repaired = repair_activity_times(conv)
    print(f"repaired_activity_times={repaired}", flush=True)

    cids = conv.list_conversation_ids()
    n = conv.batch_mark_dirty_and_enqueue_session_observe(
        cids, mark_dirty=True, immediate=True
    )
    print(f"conversations={len(cids)} enqueued_or_upgraded={n}", flush=True)

    total = 0
    empty_rounds = 0
    for i in range(300):
        done = worker.drain(max_jobs=10)
        total += done
        pending = conv.conn.execute(
            """
            SELECT COUNT(*) FROM derivation_outbox
            WHERE kind='session_observe_memory'
              AND status IN ('pending','running','blocked')
            """
        ).fetchone()[0]
        print(
            f"drain_round={i + 1} done={done} total_done={total} pending={pending}",
            flush=True,
        )
        if done == 0 and pending == 0:
            empty_rounds += 1
            if empty_rounds >= 2:
                break
        else:
            empty_rounds = 0
        if done == 0 and pending > 0:
            time.sleep(2)

    confirmed = store.list_confirmed()
    print("--- confirmed after reextract ---", flush=True)
    for f in sorted(confirmed, key=lambda x: x["slot_key"]):
        print(f"{f['slot_key']}\t{f['statement']}", flush=True)
    print(f"confirmed_count={len(confirmed)}", flush=True)


if __name__ == "__main__":
    main()
