"""一次性：按消息/回合/归档真实时间修复侧栏 updated_at 与 CAS 时钟。

用法（容器内）:
  PYTHONPATH=/app python /app/scripts/repair_conversation_activity_times.py
"""

from __future__ import annotations

from app.deps import build_container
from app.engine.conversation.activity_times import repair_activity_times
from app.settings_store import load_effective_settings


def main() -> None:
    c = build_container(load_effective_settings())
    n = repair_activity_times(c.conversations)
    print(f"repaired_conversations={n}", flush=True)
    rows = c.conversations.conn.execute(
        """
        SELECT date(updated_at) AS d, COUNT(*) AS n
        FROM conversations
        GROUP BY date(updated_at)
        ORDER BY d DESC
        """
    ).fetchall()
    for r in rows:
        print(f"updated_at_date={r['d']} count={r['n']}", flush=True)


if __name__ == "__main__":
    main()
